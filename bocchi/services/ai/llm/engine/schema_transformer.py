from abc import ABC, abstractmethod
import copy
from typing import Any


class BaseSchemaTransformer(ABC):
    """JSON Schema 节点处理器基类"""

    @abstractmethod
    def process_node(
        self, node: dict[str, Any], is_root: bool = False
    ) -> dict[str, Any]:
        """处理单个 Schema 节点并返回修改后的节点"""
        pass


class SchemaPipeline:
    """JSON Schema 转换管道执行器"""

    def __init__(self, transformers: list[BaseSchemaTransformer]):
        self.transformers = transformers

    def run(self, schema: dict[str, Any]) -> dict[str, Any]:
        """执行管道，递归遍历并处理整个 Schema AST"""
        if not isinstance(schema, dict):
            return schema
        schema_copy = copy.deepcopy(schema)
        return self._walk(schema_copy, is_root=True)

    def _walk(self, node: Any, is_root: bool = False) -> Any:
        """核心递归遍历算法，定向深入标准的 Schema 容器键"""
        if isinstance(node, list):
            return [self._walk(item, is_root=False) for item in node]
        if not isinstance(node, dict):
            return node

        current_node = node
        for transformer in self.transformers:
            current_node = transformer.process_node(current_node, is_root=is_root)
            if not isinstance(current_node, dict):
                return current_node

        for dict_key in ["properties", "patternProperties", "$defs", "definitions"]:
            if dict_key in current_node and isinstance(current_node[dict_key], dict):
                current_node[dict_key] = {
                    k: self._walk(v, is_root=False)
                    for k, v in current_node[dict_key].items()
                }

        for list_key in ["anyOf", "allOf", "oneOf", "prefixItems"]:
            if list_key in current_node and isinstance(current_node[list_key], list):
                current_node[list_key] = [
                    self._walk(v, is_root=False) for v in current_node[list_key]
                ]

        for single_key in ["items", "additionalProperties", "contains"]:
            if single_key in current_node and isinstance(
                current_node[single_key], dict
            ):
                current_node[single_key] = self._walk(
                    current_node[single_key], is_root=False
                )

        return current_node


class RootRefInlineTransformer(BaseSchemaTransformer):
    """将根节点的 $ref 展开，保留 $defs 供内部递归使用"""

    def process_node(
        self, node: dict[str, Any], is_root: bool = False
    ) -> dict[str, Any]:
        if is_root and "$ref" in node:
            ref_path = node.pop("$ref")
            ref_name = ref_path.split("/")[-1]
            defs = node.get("$defs") or node.get("definitions") or {}
            if ref_name in defs:
                def_content = defs[ref_name].copy()
                for k, v in def_content.items():
                    if k not in node:
                        node[k] = v
        return node


class RemoveUnsupportedKeysTransformer(BaseSchemaTransformer):
    """移除不支持的键"""

    def __init__(self, keys_to_remove: list[str]):
        self.keys_to_remove = keys_to_remove

    def process_node(
        self, node: dict[str, Any], is_root: bool = False
    ) -> dict[str, Any]:
        for key in self.keys_to_remove:
            node.pop(key, None)
        return node


class GeminiEnumTransformer(BaseSchemaTransformer):
    """将 const 转换为 enum (Gemini 专用)"""

    def process_node(
        self, node: dict[str, Any], is_root: bool = False
    ) -> dict[str, Any]:
        if "const" in node:
            node["enum"] = [node.pop("const")]
        return node


class GeminiNullableUnionTransformer(BaseSchemaTransformer):
    """处理 anyOf 和 type 列表中的 null，转换为 nullable: True (Gemini 专用)"""

    def process_node(
        self, node: dict[str, Any], is_root: bool = False
    ) -> dict[str, Any]:
        if "type" in node and isinstance(node["type"], list):
            types_list = node["type"]
            if "null" in types_list:
                node["nullable"] = True
                types_list = [t for t in types_list if t != "null"]
                node["type"] = types_list[0] if len(types_list) == 1 else types_list

        if "anyOf" in node and isinstance(node["anyOf"], list):
            any_of = node["anyOf"]
            has_null = any(
                isinstance(x, dict) and x.get("type") == "null" for x in any_of
            )
            if has_null:
                node["nullable"] = True
                new_any_of = [
                    x
                    for x in any_of
                    if not (isinstance(x, dict) and x.get("type") == "null")
                ]
                if len(new_any_of) == 1:
                    node.update(new_any_of[0])
                    node.pop("anyOf", None)
                else:
                    node["anyOf"] = new_any_of
        return node


class GeminiFormatTransformer(BaseSchemaTransformer):
    """清理不支持的 format 格式 (Gemini 专用)"""

    def process_node(
        self, node: dict[str, Any], is_root: bool = False
    ) -> dict[str, Any]:
        if node.get("format") and node["format"] not in ["enum", "date-time"]:
            node.pop("format", None)
        return node


class StrictObjectTransformer(BaseSchemaTransformer):
    """
    强制对象必须关闭 additionalProperties，
    并将所有 properties 设为 required (OpenAI/DeepSeek 专用)
    """

    def process_node(
        self, node: dict[str, Any], is_root: bool = False
    ) -> dict[str, Any]:
        if node.get("type") == "object" or "properties" in node:
            node["type"] = "object"
            node["additionalProperties"] = False
            if "properties" not in node:
                node["properties"] = {}
            node["required"] = list(node["properties"].keys())
        return node


class OpenAIUnionFlattenTransformer(BaseSchemaTransformer):
    """
    将 anyOf/allOf/oneOf 拍平，选取第一个非 null 的类型作为降级方案
    (OpenAI 严格模式不支持复杂 Union)
    """

    def process_node(
        self, node: dict[str, Any], is_root: bool = False
    ) -> dict[str, Any]:
        for union_key in ["anyOf", "allOf", "oneOf"]:
            if union_key in node:
                union_list = node.pop(union_key)
                if isinstance(union_list, list) and len(union_list) > 0:
                    fallback = {}
                    for item in union_list:
                        if isinstance(item, dict) and item.get("type") != "null":
                            fallback = item
                            break
                    if not fallback and isinstance(union_list[0], dict):
                        fallback = union_list[0]
                    for k, v in fallback.items():
                        if k not in node:
                            node[k] = v
        return node


class TypeEnforcerTransformer(BaseSchemaTransformer):
    """强制赋予空节点类型 (默认 string)"""

    def process_node(
        self, node: dict[str, Any], is_root: bool = False
    ) -> dict[str, Any]:
        if "type" not in node and "properties" not in node and "$ref" not in node:
            node["type"] = "string"
        return node


class DeepSeekFallbackTransformer(BaseSchemaTransformer):
    """非根空对象转为字符串 (DeepSeek 专用避坑)"""

    def process_node(
        self, node: dict[str, Any], is_root: bool = False
    ) -> dict[str, Any]:
        if node.get("type") == "object" and not is_root and not node.get("properties"):
            node["type"] = "string"
            for k in ["properties", "required", "additionalProperties"]:
                node.pop(k, None)
            node["description"] = (
                f"{node.get('description', '')} (Please provide a JSON string)".strip()
            )
        return node


class GeminiCyclicRefTransformer(BaseSchemaTransformer):
    """
    识别并处理循环引用：
    Gemini 要求循环引用的 $ref 决不能出现在父级的 required 列表中
    """

    def __init__(self, full_schema: dict):
        self.cyclic_refs = self._detect_cycles(full_schema)

    def _detect_cycles(self, schema: dict) -> set[str]:
        defs = schema.get("$defs") or schema.get("definitions") or {}
        cyclic = set()

        def check_cycle(def_name: str, visited: set, path: list):
            if def_name in path:
                for node in path[path.index(def_name) :]:
                    cyclic.add(f"#/$defs/{node}")
                    cyclic.add(f"#/definitions/{node}")
                return
            if def_name in visited:
                return
            visited.add(def_name)
            node = defs.get(def_name, {})

            def find_refs(n: Any) -> list[str]:
                refs = []
                if isinstance(n, dict):
                    if "$ref" in n:
                        refs.append(n["$ref"])
                    for v in n.values():
                        refs.extend(find_refs(v))
                elif isinstance(n, list):
                    for v in n:
                        refs.extend(find_refs(v))
                return refs

            for ref in find_refs(node):
                if ref.startswith("#/$defs/") or ref.startswith("#/definitions/"):
                    next_def = ref.split("/")[-1]
                    check_cycle(next_def, visited, [*path, def_name])

        visited_set = set()
        for name in defs:
            check_cycle(name, visited_set, [])
        return cyclic

    def process_node(
        self, node: dict[str, Any], is_root: bool = False
    ) -> dict[str, Any]:
        if "properties" in node and isinstance(node.get("required"), list):
            new_required = []
            for req_key in node["required"]:
                prop = node.get("properties", {}).get(req_key, {})
                is_cyclic = False
                if prop.get("$ref") in self.cyclic_refs:
                    is_cyclic = True
                elif prop.get("type") == "array" and isinstance(
                    prop.get("items"), dict
                ):
                    if prop["items"].get("$ref") in self.cyclic_refs:
                        is_cyclic = True
                if not is_cyclic:
                    new_required.append(req_key)
            if not new_required:
                node.pop("required")
            else:
                node["required"] = new_required
        return node


class RefComplianceTransformer(BaseSchemaTransformer):
    """如果包含 $ref，同级不允许出现任何非 $ 开头的键 (如 description, title)"""

    def process_node(
        self, node: dict[str, Any], is_root: bool = False
    ) -> dict[str, Any]:
        if "$ref" in node:
            keys_to_remove = [k for k in node.keys() if not k.startswith("$")]
            for k in keys_to_remove:
                node.pop(k)
        return node


class GeminiDeepRefInlineTransformer(BaseSchemaTransformer):
    """
    深度展开所有 $ref，并清理 $defs (Gemini Function Calling 专用)。
    大模型 API 网关层面严格拒绝 $defs 与 $ref，所以进行全量物理替换。
    如果遇到循环引用，将安全退化为 string 类型防止栈溢出死循环。
    """

    def process_node(
        self, node: dict[str, Any], is_root: bool = False
    ) -> dict[str, Any]:
        if not is_root:
            return node

        defs = {}
        if "$defs" in node:
            defs.update(node["$defs"])
        if "definitions" in node:
            defs.update(node["definitions"])

        def _resolve_refs(current: Any, visited: set) -> Any:
            if isinstance(current, list):
                return [_resolve_refs(item, visited) for item in current]
            elif isinstance(current, dict):
                if "$ref" in current:
                    ref_path = current["$ref"]
                    ref_name = ref_path.split("/")[-1]
                    if ref_name in defs:
                        if ref_name in visited:
                            return {
                                "type": "string",
                                "description": "Cyclic reference omitted",
                            }

                        new_visited = visited | {ref_name}
                        resolved = _resolve_refs(defs[ref_name], new_visited)

                        result = current.copy()
                        result.pop("$ref")
                        for k, v in resolved.items():
                            if k not in result:
                                result[k] = v
                        return result
                return {k: _resolve_refs(v, visited) for k, v in current.items()}
            return current

        node = _resolve_refs(node, set())
        node.pop("$defs", None)
        node.pop("definitions", None)
        return node
