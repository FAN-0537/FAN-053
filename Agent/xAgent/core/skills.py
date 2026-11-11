"""Agent Skills 发现与动态加载。

初始化阶段只读取各 Skill 的 SKILL.md 前置元数据（name、description），
完整正文和附件只有在模型调用 loadSkill 时才读取，以保持上下文精简。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from core.filesystem.support import (
    MAX_TEXT_FILE_BYTES,
    detect_text_encoding,
    error,
    ok,
)

SKILLS_RELATIVE_PATH = Path(".agents") / "skills"
SKILL_FILE_NAME = "SKILL.md"
FRONTMATTER_DELIMITER = "---"
MAX_SKILL_NAME_LENGTH = 64
MAX_SKILL_DESCRIPTION_LENGTH = 1024
SKILL_NAME_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def normalize_skill_name(value: str) -> str:
    """把输入规范化为小写字母、数字和连字符组成的 Skill 名称。"""

    text = str(value or "").strip().lower()
    text = re.sub(r"[\s_]+", "-", text)
    text = re.sub(r"[^a-z0-9-]", "-", text)
    text = re.sub(r"-{2,}", "-", text)
    return text.strip("-")


@dataclass(frozen=True, slots=True)
class Skill:
    name: str
    description: str
    directory: Path
    skill_file: Path


def _read_frontmatter(path: Path) -> dict[str, str]:
    """只读取 SKILL.md 开头的 YAML Frontmatter，不加载正文。"""

    encoding = detect_text_encoding(path)
    if not encoding:
        return {}

    try:
        with path.open("r", encoding=encoding, newline="") as file:
            first_line = file.readline()
            if first_line.lstrip("\ufeff").strip() != FRONTMATTER_DELIMITER:
                return {}

            lines: list[str] = []
            for line in file:
                if line.strip() == FRONTMATTER_DELIMITER:
                    break
                lines.append(line.rstrip("\r\n"))
            else:
                return {}
    except (OSError, UnicodeDecodeError):
        return {}

    return _parse_frontmatter_lines(lines)


def _parse_frontmatter_lines(lines: list[str]) -> dict[str, str]:
    data: dict[str, str] = {}
    index = 0

    while index < len(lines):
        line = lines[index]
        index += 1
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if line[:1].isspace():
            continue
        if ":" not in line:
            continue

        key, raw_value = line.split(":", 1)
        key = key.strip()
        value = raw_value.strip()

        is_block = value in {"|", "|-", "|+", ">", ">-", ">+"}
        if key not in {"name", "description"}:
            if is_block:
                while index < len(lines):
                    next_line = lines[index]
                    if next_line.strip() and not next_line[:1].isspace():
                        break
                    index += 1
            continue

        if is_block:
            block_lines: list[str] = []
            while index < len(lines):
                next_line = lines[index]
                if next_line.strip() and not next_line[:1].isspace():
                    break
                block_lines.append(next_line)
                index += 1
            data[key] = _parse_block_scalar(block_lines, folded=value.startswith(">"))
        else:
            data[key] = _unquote(_strip_inline_comment(value))

    return data


def _strip_inline_comment(value: str) -> str:
    in_single = False
    in_double = False
    for index, char in enumerate(value):
        if char == "'" and not in_double:
            in_single = not in_single
        elif char == '"' and not in_single:
            in_double = not in_double
        elif (
            char == "#"
            and not in_single
            and not in_double
            and (index == 0 or value[index - 1].isspace())
        ):
            return value[:index].rstrip()
    return value


def _unquote(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] == '"':
        try:
            return str(json.loads(value))
        except (json.JSONDecodeError, TypeError):
            return value[1:-1]
    if len(value) >= 2 and value[0] == value[-1] == "'":
        return value[1:-1].replace("''", "'")
    return value


def _parse_block_scalar(lines: list[str], *, folded: bool) -> str:
    indents = [
        len(line) - len(line.lstrip(" "))
        for line in lines
        if line.strip()
    ]
    indent = min(indents) if indents else 0
    cleaned = [line[indent:] if len(line) >= indent else "" for line in lines]
    while cleaned and not cleaned[-1].strip():
        cleaned.pop()

    if not folded:
        return "\n".join(cleaned).strip()

    parts: list[str] = []
    previous_blank = False
    for line in cleaned:
        if not line.strip():
            parts.append("\n")
            previous_blank = True
            continue
        if parts and not previous_blank:
            parts.append(" ")
        parts.append(line.strip())
        previous_blank = False
    return "".join(parts).strip()


def _split_frontmatter_text(text: str) -> tuple[list[str] | None, str]:
    """拆分 SKILL.md 文本为 Frontmatter 行与正文。"""

    normalized = text.lstrip("\ufeff")
    lines = normalized.splitlines()
    if not lines or lines[0].strip() != FRONTMATTER_DELIMITER:
        return None, normalized

    for index in range(1, len(lines)):
        if lines[index].strip() == FRONTMATTER_DELIMITER:
            return lines[1:index], "\n".join(lines[index + 1 :])
    return None, normalized


def _extra_frontmatter_lines(lines: list[str]) -> list[str]:
    """保留 name/description 之外的其他 Frontmatter 字段。"""

    extras: list[str] = []
    index = 0
    while index < len(lines):
        line = lines[index]
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or line[:1].isspace():
            extras.append(line)
            index += 1
            continue
        if ":" not in line:
            extras.append(line)
            index += 1
            continue

        block = [line]
        key = line.split(":", 1)[0].strip()
        index += 1
        while index < len(lines):
            next_line = lines[index]
            if next_line.strip() and not next_line[:1].isspace():
                break
            block.append(next_line)
            index += 1
        if key not in {"name", "description"}:
            extras.extend(block)

    while extras and not extras[0].strip():
        extras.pop(0)
    while extras and not extras[-1].strip():
        extras.pop()
    return extras


def _yaml_quote(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def _derive_description(
    body: str,
    max_length: int = MAX_SKILL_DESCRIPTION_LENGTH,
) -> str:
    for line in body.splitlines():
        text = line.strip()
        if not text:
            continue
        text = re.sub(r"^#{1,6}\s*", "", text)
        text = re.sub(r"^(?:[-*+]|\d+\.)\s+", "", text)
        text = re.sub(r"\s+", " ", text).strip()
        if text:
            return text[:max_length]
    return ""


def _is_within(path: Path, directory: Path) -> bool:
    try:
        path.relative_to(directory)
    except ValueError:
        return False
    return True


def _read_text_file(
    path: Path,
    max_bytes: int = MAX_TEXT_FILE_BYTES,
) -> tuple[str | None, dict[str, Any] | None]:
    try:
        size = path.stat().st_size
    except OSError as exc:
        return None, error(f"读取文件信息失败: {exc}")
    if size > max_bytes:
        return None, error(f"文件过大（{size} 字节），暂不支持读取")

    encoding = detect_text_encoding(path)
    if not encoding:
        return None, error("仅支持读取纯文本文件，该文件可能是二进制文件或编码不受支持")

    try:
        content = path.read_text(encoding=encoding, newline="")
    except (OSError, UnicodeDecodeError) as exc:
        return None, error(f"读取文件失败: {exc}")
    return content, None


class SkillManager:
    """发现并动态加载项目中的 Agent Skills。"""

    def __init__(
        self,
        root: str | Path | None = None,
        skills_dir: str | Path | None = None,
        *,
        max_text_file_bytes: int = MAX_TEXT_FILE_BYTES,
        max_name_length: int = MAX_SKILL_NAME_LENGTH,
        max_description_length: int = MAX_SKILL_DESCRIPTION_LENGTH,
    ) -> None:
        self.root = (
            Path(root) if root is not None else Path.cwd()
        ).expanduser().resolve()
        if skills_dir is not None:
            self.skills_dir = Path(skills_dir).expanduser().resolve()
        else:
            self.skills_dir = (self.root / SKILLS_RELATIVE_PATH).resolve()
        self.max_text_file_bytes = max(1, int(max_text_file_bytes))
        self.max_name_length = max(1, int(max_name_length))
        self.max_description_length = max(1, int(max_description_length))
        self._skills: dict[str, Skill] = {}
        self.discover()

    @property
    def skills(self) -> list[Skill]:
        return sorted(self._skills.values(), key=lambda skill: skill.name.lower())

    def discover(self) -> None:
        """扫描 skills 目录，只登记 name 和 description。"""

        self._skills.clear()
        if not self.skills_dir.is_dir():
            return

        try:
            entries = sorted(
                self.skills_dir.iterdir(),
                key=lambda item: item.name.lower(),
            )
        except OSError:
            return

        for entry in entries:
            if not entry.is_dir():
                continue
            skill_file = entry / SKILL_FILE_NAME
            if not skill_file.is_file():
                continue

            metadata = _read_frontmatter(skill_file)
            name = str(metadata.get("name", "")).strip()
            description = str(metadata.get("description", "")).strip()
            if not name or not description or name in self._skills:
                continue

            try:
                self._skills[name] = Skill(
                    name=name,
                    description=description,
                    directory=entry.resolve(),
                    skill_file=skill_file.resolve(),
                )
            except OSError:
                continue

    def create_skill(self, name: str, skill_context: str) -> dict[str, Any]:
        """根据名称和完整上下文创建符合 Agent Skills 规范的 SKILL.md。"""

        normalized = normalize_skill_name(name)
        if not normalized:
            return error(
                "Skill 名称必须由小写英文字母、数字和连字符组成，例如 pdf-processing"
            )
        if len(normalized) > self.max_name_length:
            return error(
                f"Skill 名称过长（{len(normalized)} 字符），"
                f"最多 {self.max_name_length} 字符"
            )
        if not SKILL_NAME_PATTERN.match(normalized):
            return error(
                "Skill 名称必须由小写英文字母、数字和连字符组成，"
                "且不能以连字符开头或结尾，例如 pdf-processing"
            )

        if not isinstance(skill_context, str) or not skill_context.strip():
            return error("参数 skillContext 不能为空，需要提供 SKILL.md 的完整内容")

        directory = (self.skills_dir / normalized).resolve()
        skill_file = directory / SKILL_FILE_NAME
        existing = self.get(normalized)
        if directory.exists() or skill_file.exists() or existing is not None:
            location = existing.skill_file if existing is not None else skill_file
            return error(
                f"Skill '{normalized}' 已存在（{location}），为避免覆盖原有内容，本次未做任何修改"
            )

        frontmatter_lines, body = _split_frontmatter_text(skill_context)
        metadata = (
            _parse_frontmatter_lines(frontmatter_lines)
            if frontmatter_lines is not None
            else {}
        )
        description = str(metadata.get("description", "")).strip()
        if not description:
            description = _derive_description(body, self.max_description_length)
        if not description:
            return error(
                "无法确定 Skill 的 description：请在 skillContext 中提供正文，"
                "或在 Frontmatter 中提供 description 字段"
            )
        if len(description) > self.max_description_length:
            description = description[: self.max_description_length].rstrip()

        extras = (
            _extra_frontmatter_lines(frontmatter_lines)
            if frontmatter_lines is not None
            else []
        )
        frontmatter = [
            FRONTMATTER_DELIMITER,
            f"name: {_yaml_quote(normalized)}",
            f"description: {_yaml_quote(description)}",
            *extras,
            FRONTMATTER_DELIMITER,
        ]
        body_text = body.strip("\n")
        content = "\n".join(frontmatter) + "\n\n" + body_text + "\n"

        try:
            directory.mkdir(parents=True, exist_ok=False)
        except FileExistsError:
            return error(
                f"Skill 目录已存在（{directory}），为避免覆盖原有内容，本次未做任何修改"
            )
        except OSError as exc:
            return error(f"创建 Skill 目录失败: {exc}")

        try:
            with skill_file.open("x", encoding="utf-8", newline="") as file:
                file.write(content)
        except FileExistsError:
            return error(
                f"SKILL.md 已存在（{skill_file}），为避免覆盖原有内容，本次未做任何修改"
            )
        except OSError as exc:
            return error(f"写入 SKILL.md 失败: {exc}")

        self.discover()
        return ok(
            name=normalized,
            description=description,
            directory=str(directory),
            path=str(skill_file),
            created=True,
        )

    def get(self, name: str) -> Skill | None:
        skill = self._skills.get(str(name or "").strip())
        if skill is not None:
            return skill

        normalized = str(name or "").strip().lower()
        for candidate in self._skills.values():
            if candidate.name.lower() == normalized:
                return candidate
        return None

    def render_system_prompt(self) -> str:
        """生成注入 System Prompt 的 Skill 目录说明。"""

        if not self._skills:
            return ""

        lines = ["You have access to the following skills:"]
        for skill in self.skills:
            description = " ".join(skill.description.split())
            lines.append(f"- '{skill.name}': {description}")
        lines.extend(
            [
                "",
                "Use the 'loadSkill' tool to load the full instructions of a skill "
                "when needed. You can also load additional files referenced by a skill.",
            ]
        )
        return "\n".join(lines)

    def load_skill(self, name: str, filename: str | None = None) -> dict[str, Any]:
        """读取 Skill 正文或 Skill 目录内的附件文件。"""

        skill = self.get(name)
        if skill is None:
            available = ", ".join(skill.name for skill in self.skills) or "（无）"
            return error(f"未知 Skill: {name}。可用 Skill: {available}")

        if filename is None or not str(filename).strip():
            target = skill.skill_file
        else:
            target, failure, candidates = self._resolve_attachment(
                skill,
                str(filename),
            )
            if candidates:
                relative_candidates = [
                    self._relative_name(path, skill.directory) for path in candidates
                ]
                return ok(
                    name=skill.name,
                    filename=str(filename),
                    ambiguous=True,
                    candidates=relative_candidates,
                    message="找到多个同名文件，请提供更完整的 filename 以指定要读取的文件",
                )
            if failure is not None:
                return failure
            assert target is not None

        content, failure = _read_text_file(target, self.max_text_file_bytes)
        if failure is not None:
            return failure

        return ok(
            name=skill.name,
            path=str(target),
            filename=self._relative_name(target, skill.directory),
            content=content,
        )

    def _resolve_attachment(
        self,
        skill: Skill,
        filename: str,
    ) -> tuple[Path | None, dict[str, Any] | None, list[Path] | None]:
        path = Path(filename).expanduser()
        skill_dir = skill.directory
        is_bare_name = not path.is_absolute() and path.parent == Path(".")

        if path.is_absolute():
            candidates = [path]
        else:
            candidates = [skill_dir / path, self.root / path]

        outside_path: Path | None = None
        seen: set[Path] = set()
        for candidate in candidates:
            try:
                resolved = candidate.resolve()
            except OSError:
                continue
            if resolved in seen:
                continue
            seen.add(resolved)

            if not _is_within(resolved, skill_dir):
                outside_path = resolved
                continue
            if resolved.is_file():
                return resolved, None, None

        if not is_bare_name:
            if outside_path is not None:
                return (
                    None,
                    error(f"文件路径超出 Skill 目录范围: {filename}"),
                    None,
                )
            return None, error(f"Skill '{skill.name}' 中不存在文件: {filename}"), None

        try:
            matches = sorted(
                {
                    item.resolve()
                    for item in skill_dir.rglob(path.name)
                    if item.is_file()
                }
            )
        except OSError as exc:
            return None, error(f"搜索 Skill 文件失败: {exc}"), None

        if len(matches) == 1:
            return matches[0], None, None
        if len(matches) > 1:
            return None, None, matches
        return None, error(f"Skill '{skill.name}' 中不存在文件: {filename}"), None

    @staticmethod
    def _relative_name(path: Path, directory: Path) -> str:
        try:
            return path.relative_to(directory).as_posix()
        except ValueError:
            return str(path)
