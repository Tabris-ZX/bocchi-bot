from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from bocchi.services.ai.sandbox.models import SandboxBlueprint
from bocchi.utils.pydantic_compat import model_validator

DisclosureLevel = Annotated[
    Literal[1, 2, 3], "Progressive disclosure levels for skill loading."
]
METADATA: DisclosureLevel = 1
INSTRUCTIONS: DisclosureLevel = 2
RESOURCES: DisclosureLevel = 3


class SkillEnvConfig(BaseModel):
    """全量技能环境变量配置根节点"""

    envs: dict[str, dict[str, dict[str, str]]] = Field(default_factory=dict)


class SkillFrontmatter(BaseModel):
    model_config = ConfigDict(populate_by_name=True)  # type: ignore

    name: str = Field(...)
    """技能名称"""
    description: str = Field(...)
    """技能描述"""
    compatibility: str | None = Field(default=None)
    """环境要求"""
    metadata: dict[str, Any] | None = Field(default=None)
    """自定义元数据"""
    allowed_tools: list[str] | None = Field(default=None, alias="allowed-tools")
    """允许的工具"""
    permissions: dict[str, Any] | None = Field(default=None)
    """沙箱权限声明 (如 network: true/false)"""
    blueprint: SandboxBlueprint = Field(default_factory=SandboxBlueprint)
    """统一环境装配蓝图声明 (根据 metadata 等自动推导)"""
    required_envs: list[str] = Field(default_factory=list)
    """声明该技能必需的全局环境变量 Key"""

    @model_validator(mode="before")
    @classmethod
    def parse_allowed_tools(cls, values: dict[str, Any]) -> dict[str, Any]:
        """将字符串格式的 allowed-tools 按空格切分为列表"""
        key = "allowed-tools"
        alt_key = "allowed_tools"
        raw = values.get(key) or values.get(alt_key)
        if isinstance(raw, str):
            values[key] = raw.split()
        return values

    @property
    def enable_network(self) -> bool:
        """网络权限：默认开启（高信任静态资产），
        允许在 YAML 中通过 permissions.network 显式关闭"""
        if self.permissions and isinstance(self.permissions, dict):
            return self.permissions.get("network", True)
        return True


class Skill(BaseModel):
    frontmatter: SkillFrontmatter
    """解析后的YAML元数据"""
    instructions: str | None = Field(default=None)
    """SKILL.md正文指令，在INSTRUCTIONS级别填充"""
    path: Path
    """技能所在目录"""
    disclosure_level: DisclosureLevel = Field(default=METADATA)
    """当前披露等级"""
    scripts: list[str] = Field(default_factory=list)
    """脚本文件列表"""
    references: list[str] = Field(default_factory=list)
    """参考文档列表"""
    source: str = Field(default="local")
    """技能来源提供者标识"""
    namespace: str = Field(default="global")
    """隔离所属的插件命名空间"""

    def with_disclosure_level(
        self,
        level: DisclosureLevel,
        instructions: str | None = None,
        scripts: list[str] | None = None,
        references: list[str] | None = None,
    ) -> "Skill":
        """创建一个提升了披露等级的全新 Skill 实例"""
        return Skill(
            frontmatter=self.frontmatter,
            instructions=instructions
            if instructions is not None
            else self.instructions,
            path=self.path,
            disclosure_level=level,
            scripts=scripts if scripts is not None else self.scripts,
            references=references if references is not None else self.references,
            source=self.source,
            namespace=self.namespace,
        )

    @property
    def id(self) -> str:
        """技能的唯一标识符（强制使用所在文件夹的名称）"""
        return self.path.name

    def to_xml(self) -> str:
        """将技能转化为结构化的 XML 格式，供大模型友好读取"""
        xml = f"<skill>\n  <name>{self.id}</name>\n  <description>{self.description}</description>\n"  # noqa: E501
        if self.instructions:
            xml += f"  <instructions>\n{self.instructions}\n  </instructions>\n"
        if self.scripts:
            xml += (
                "  <available_scripts>\n"
                + "\n".join(f"    <script>{s}</script>" for s in self.scripts)
                + "\n  </available_scripts>\n"
            )
        if self.references:
            xml += (
                "  <available_references>\n"
                + "\n".join(f"    <reference>{r}</reference>" for r in self.references)
                + "\n  </available_references>\n"
            )
        xml += "</skill>"
        return xml

    @property
    def name(self) -> str:
        """技能的显示名称（来自 YAML，可能不符合规范）"""
        return self.frontmatter.name

    @property
    def description(self) -> str:
        return self.frontmatter.description


class SkillSource(BaseModel):
    """显式定义的技能源 (动态解析器)"""

    fetch_all: bool = Field(default=False)
    """是否拉取全局所有已注册的技能"""
    scan_dir: Path | None = Field(default=None)
    """扫描特定物理目录下的所有技能"""
    exclude_skills: list[str] | None = Field(default=None)
    """需要排除的技能 ID 列表"""

    @classmethod
    def all(cls, exclude: list[str] | None = None) -> "SkillSource":
        """声明式：获取系统全局挂载目录下的所有技能"""
        return cls(fetch_all=True, exclude_skills=exclude)

    @classmethod
    def from_dir(
        cls, path: str | Path, exclude: list[str] | None = None
    ) -> "SkillSource":
        """声明式：获取指定物理目录下的所有技能（支持私有独立技能库）"""
        from pathlib import Path

        return cls(scan_dir=Path(path), exclude_skills=exclude)


class SkillBlueprintBuilder:
    """环境蓝图组装器：将 YAML 字典剥离解析为沙箱 Blueprint 和环境变量要求"""

    @classmethod
    def build(cls, values: dict[str, Any]) -> tuple[SandboxBlueprint, list[str]]:
        env_setup_data = values.get("env_setup", {})
        python_packages = env_setup_data.get("python_packages", [])
        system_packages = env_setup_data.get("system_packages", [])
        node_packages = env_setup_data.get("node_packages", [])
        bins = env_setup_data.get("bins", [])
        install_scripts = env_setup_data.get("install_scripts", [])
        required_envs = values.get("required_envs", [])

        metadata = values.get("metadata", {})
        if isinstance(metadata, str):
            import json

            try:
                metadata = json.loads(metadata)
            except Exception:
                metadata = {}

        if isinstance(metadata, dict):
            for data in metadata.values():
                if not isinstance(data, dict):
                    continue
                requires = data.get("requires", {})
                if isinstance(requires, dict):
                    for bin_key in ("bins", "anyBins"):
                        b = requires.get(bin_key, [])
                        if isinstance(b, list):
                            bins.extend(b)
                    envs = requires.get("env", [])
                    if isinstance(envs, list):
                        required_envs.extend(envs)

                installs = data.get("install", [])
                if isinstance(installs, list):
                    for inst in installs:
                        if not isinstance(inst, dict):
                            continue
                        kind = inst.get("kind", "").lower()
                        if kind in ("python", "pip", "uv"):
                            pkg = inst.get("package", "")
                            if isinstance(pkg, str) and pkg:
                                python_packages.extend(pkg.split())
                        elif kind in ("node", "npm"):
                            pkg = inst.get("package", "")
                            if isinstance(pkg, str) and pkg:
                                node_packages.append(pkg)
                        elif kind in ("apt"):
                            pkg = inst.get("formula") or inst.get("package") or ""
                            if isinstance(pkg, str) and pkg:
                                pkg_name = pkg.split("/")[-1]
                                system_packages.append(pkg_name)
                        elif kind == "go":
                            mod = inst.get("module", "")
                            if isinstance(mod, str) and mod:
                                install_scripts.append(f"go install {mod}")

        key = "allowed-tools"
        alt_key = "allowed_tools"
        raw_tools = values.get(key) or values.get(alt_key)
        tools_list = (
            raw_tools.split()
            if isinstance(raw_tools, str)
            else (raw_tools if isinstance(raw_tools, list) else [])
        )

        import re

        for tool in tools_list:
            if isinstance(tool, str) and tool.startswith("Bash("):
                match = re.search(r"Bash\((.*?)\)", tool)
                if match:
                    inner = match.group(1)
                    cmd = inner.split(":")[0]
                    if cmd not in bins:
                        bins.append(cmd)

        from bocchi.services.ai.sandbox.models import (
            AptSetup,
            NodeSetup,
            PythonSetup,
            ShellSetup,
        )

        steps = []
        if system_packages:
            steps.append(AptSetup(packages=list(dict.fromkeys(system_packages))))
        if python_packages:
            steps.append(PythonSetup(packages=list(dict.fromkeys(python_packages))))
        if node_packages:
            steps.append(NodeSetup(packages=list(dict.fromkeys(node_packages))))
        if install_scripts:
            steps.append(ShellSetup(scripts=install_scripts))

        blueprint = SandboxBlueprint(setup_steps=steps)
        return blueprint, list(dict.fromkeys(required_envs))
