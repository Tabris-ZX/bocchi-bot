import re

from .models import ParsedNode, UserSource


def _extract_nested_content(text: str) -> tuple[str, str, str]:
    try:
        start_idx = text.index("{")
        brace_level = 0
        end_idx = -1
        for i in range(start_idx, len(text)):
            if text[i] == "{":
                brace_level += 1
            elif text[i] == "}":
                brace_level -= 1
                if brace_level == 0:
                    end_idx = i
                    break

        if end_idx == -1:
            return "", text, ""

        prefix = text[:start_idx]
        nested_content = text[start_idx + 1:end_idx].strip()
        suffix = text[end_idx + 1:].strip()
        return nested_content, prefix, suffix
    except ValueError:
        return "", text, ""

def _split_content_by_pipe(content: str) -> list[str]:
    parts = []
    current_part = ""
    brace_level = 0
    for char in content:
        if char == "{":
            brace_level += 1
        elif char == "}":
            brace_level -= 1

        if char == "|" and brace_level == 0:
            parts.append(current_part.strip())
            current_part = ""
        else:
            current_part += char

    parts.append(current_part.strip())
    return parts

def parse_content(content: str, at_qq_list: list[str]) -> tuple[list[ParsedNode], int]:
    nodes: list[ParsedNode] = []
    at_used_count = 0

    for part in _split_content_by_pipe(content):
        nested_content, prefix, suffix = _extract_nested_content(part)

        user_qq = ""
        text_content = ""
        source: UserSource = UserSource.RAW_ID

        match = re.match(r"^(\d{6,11})?说", prefix)
        if match:
            possible_qq = match.group(1)
            if possible_qq:
                user_qq = possible_qq
                source = UserSource.RAW_ID
            elif at_used_count < len(at_qq_list):
                user_qq = at_qq_list[at_used_count]
                at_used_count += 1
                source = UserSource.AT_MENTION
            text_content = prefix[match.end():].strip()
        else:
            if at_used_count < len(at_qq_list):
                user_qq = at_qq_list[at_used_count]
                at_used_count += 1
                source = UserSource.AT_MENTION
                text_content = prefix.strip()

        if not user_qq:
            continue

        node = ParsedNode(uin=user_qq, source=source)
        if text_content:
            node.content.append(text_content)

        if nested_content:
            nested_nodes, nested_at_used = parse_content(
                nested_content, at_qq_list[at_used_count:]
            )
            node.content.extend(nested_nodes)
            at_used_count += nested_at_used

        if suffix:
            node.content.append(suffix)

        nodes.append(node)

    return nodes, at_used_count
