import asyncio

from core.context import ContextArchive
from core.events import AgentEventType
from core.filesystem.service import FileSystemService
from core.llm.base import AssistantMessage, ToolCall
from core.skills import SkillManager
from core.tools.base import ToolRegistry
from core.tools.misc_tools import register_misc_tools
from core.agent import AgentSession


def test_leap_year_rules() -> None:
    from core.tools.misc_tools import is_leap_year

    assert is_leap_year(2024) is True
    assert is_leap_year(1900) is False
    assert is_leap_year(2000) is True
    assert is_leap_year(2023) is False


def test_filesystem_covers_ten_semantics(tmp_path) -> None:
    service = FileSystemService(tmp_path)

    assert service.get_current_directory()["cwd"] == str(tmp_path.resolve())

    created = service.create_file(".", "note.txt", "hello")
    assert created["ok"] is True
    assert (tmp_path / "note.txt").read_text(encoding="utf-8") == "hello"

    again = service.create_file(".", "note.txt", "x")
    assert again["ok"] is False

    assert service.list_directory(".")["count"] >= 1
    assert service.get_file_type("note.txt")["file_type"] == "text"
    assert service.read_file("note.txt", max_chars=2)["truncated"] is True

    assert service.edit_file("note.txt", " world", mode="append")["ok"] is True
    assert "world" in (tmp_path / "note.txt").read_text(encoding="utf-8")
    replaced = service.edit_file(
        "note.txt", mode="replace", old_text="world", new_text="earth"
    )
    assert replaced["replaced"] == 1

    assert service.create_directory("sub/inner")["ok"] is True
    assert service.rename_item("sub", "renamed")["ok"] is True
    assert (tmp_path / "renamed" / "inner").is_dir()

    assert service.delete_file("note.txt")["ok"] is True
    assert not (tmp_path / "note.txt").exists()
    assert service.delete_directory("renamed")["ok"] is True
    assert not (tmp_path / "renamed").exists()


def test_filesystem_guard_blocks_workspace_root(tmp_path) -> None:
    service = FileSystemService(tmp_path)
    assert service.delete_directory(".")["ok"] is False
    assert service.rename_item(".", "other")["ok"] is False


def test_skill_create_discover_load_and_reject_duplicate(tmp_path) -> None:
    manager = SkillManager(tmp_path)
    created = manager.create_skill(
        "pdf-processing",
        "---\ndescription: 处理 PDF 文档\n---\n# PDF\n按步骤处理 PDF。",
    )
    assert created["ok"] is True
    assert (tmp_path / ".agents" / "skills" / "pdf-processing" / "SKILL.md").is_file()

    loaded = manager.load_skill("pdf-processing")
    assert loaded["ok"] is True
    assert "按步骤处理 PDF" in loaded["content"]

    duplicate = manager.create_skill("pdf-processing", "# other")
    assert duplicate["ok"] is False

    escape = manager.load_skill("pdf-processing", "../../secret.txt")
    assert escape["ok"] is False

    prompt = manager.render_system_prompt()
    assert "pdf-processing" in prompt
    assert "处理 PDF 文档" in prompt


def test_context_archive_recall(tmp_path) -> None:
    archive = ContextArchive(tmp_path)
    archive_id = archive.save(
        [{"role": "user", "content": "部署步骤是先安装依赖"}], "20260101-000000"
    )
    result = archive.recall("部署步骤", archive_id)
    assert result["ok"] is True
    assert result["matches"]
    assert "安装依赖" in result["matches"][0]["snippet"]


class FakeLLM:
    def __init__(self) -> None:
        self.calls = 0

    async def complete(self, messages, tools=None):
        self.calls += 1
        if self.calls == 1:
            return AssistantMessage(
                content=None,
                tool_calls=(ToolCall("call-1", "isLeapYear", '{"year": 2000}'),),
            )
        return AssistantMessage(content="2000 年是闰年")

    def context_window(self):
        return 100000, False


def test_agent_tool_loop_feeds_result_back(tmp_path) -> None:
    registry = ToolRegistry()
    register_misc_tools(registry)
    llm = FakeLLM()
    session = AgentSession(llm=llm, tools=registry, workspace=tmp_path, max_tool_rounds=4)

    async def collect():
        events = []
        async for event in session.send("2000年是闰年吗"):
            events.append(event)
        return events

    events = asyncio.run(collect())
    types = [event.type for event in events]
    assert AgentEventType.TOOL_CALL in types
    assert AgentEventType.TOOL_RESULT in types
    assert AgentEventType.ASSISTANT_MESSAGE in types
    tool_messages = [m for m in session.history if m.get("role") == "tool"]
    assert tool_messages
    assert "闰年" in tool_messages[0]["content"]
