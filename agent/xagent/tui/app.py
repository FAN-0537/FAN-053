"""Textual TUI 界面。

界面层只负责渲染 AgentEvent 和收集用户输入，
所有业务逻辑均位于 core，便于未来复用同一核心实现 Web 或 Desktop 界面。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from rich.text import Text
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import (
    Button,
    Footer,
    Header,
    Input,
    Markdown,
    OptionList,
    Static,
)
from textual.widgets.option_list import Option

from core.bootstrap import AgentRuntime
from core.events import AgentEvent, AgentEventType
from core.mcp.loader import describe_manager, load_mcp_async
from core.sessions import PROJECT_CONTEXT_PREFIX, SessionSummary

SLASH_COMMANDS: list[tuple[str, str]] = [
    ("/help", "显示所有斜杠命令"),
    ("/new", "新建会话并自动保存当前会话"),
    ("/resume", "选择并恢复历史会话"),
    ("/save", "保存当前会话"),
    ("/compact", "压缩当前上下文"),
    ("/status", "查看会话、上下文与 MCP 状态"),
    ("/mcp", "查看 MCP 服务器与可用工具"),
    ("/quit", "保存并退出 xAgent"),
]


def _format_json(value: Any, *, max_chars: int = 6000) -> str:
    try:
        text = json.dumps(value, ensure_ascii=False, indent=2)
    except (TypeError, ValueError):
        text = str(value)
    if len(text) > max_chars:
        return text[:max_chars] + "\n…（内容已截断）"
    return text


def _format_tool_result(raw: str, max_chars: int = 6000) -> str:
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        text = raw
        return text[:max_chars] + ("\n…（内容已截断）" if len(text) > max_chars else "")
    return _format_json(value, max_chars=max_chars)


def _format_k(tokens: int) -> str:
    return f"{tokens / 1000:.1f}k"


class ChatMessage(Vertical):
    def __init__(self, role: str, title: str, body: str) -> None:
        super().__init__(classes=f"message {role}")
        self._role = role
        self._title = title
        self._body = body

    def compose(self) -> ComposeResult:
        yield Static(Text(self._title), classes="message-title")
        if self._role == "assistant":
            yield Markdown(self._body, classes="message-body")
        else:
            yield Static(Text(self._body), classes="message-body")


class CompactionScreen(ModalScreen[None]):
    """压缩前后对比的浮动面板。"""

    BINDINGS = [Binding("escape", "close_panel", "关闭")]

    DEFAULT_CSS = """
    CompactionScreen {
        align: center middle;
        background: $background 60%;
    }

    #compact-title {
        height: 1;
        padding: 0 1;
        text-align: center;
        text-style: bold;
        background: $primary;
        color: $text;
    }

    #compact-columns {
        width: 98%;
        height: 1fr;
    }

    .compact-column {
        width: 1fr;
        height: 1fr;
        border: round $primary;
        margin: 0 1;
    }

    .compact-head {
        height: 1;
        padding: 0 1;
        text-style: bold;
        background: $panel;
    }

    .compact-scroll {
        height: 1fr;
        padding: 0 1;
    }

    .compact-body {
        width: 100%;
        height: auto;
    }

    #compact-close {
        width: 16;
        margin: 1 0;
    }
    """

    def __init__(self, before: str, after: str) -> None:
        super().__init__()
        self._before = before
        self._after = after

    def compose(self) -> ComposeResult:
        yield Static(
            "上下文压缩预览 · 左：压缩前原文 / 右：压缩后摘要",
            id="compact-title",
        )
        with Horizontal(id="compact-columns"):
            with Vertical(classes="compact-column"):
                yield Static("压缩前原文", classes="compact-head")
                yield VerticalScroll(
                    Static(Text(self._before), classes="compact-body"),
                    classes="compact-scroll",
                )
            with Vertical(classes="compact-column"):
                yield Static("压缩后摘要", classes="compact-head")
                yield VerticalScroll(
                    Static(Text(self._after), classes="compact-body"),
                    classes="compact-scroll",
                )
        yield Button("关闭", id="compact-close", variant="primary")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "compact-close":
            self.dismiss(None)

    def action_close_panel(self) -> None:
        self.dismiss(None)


class ResumeScreen(ModalScreen[str | None]):
    """历史会话选择面板：↑/↓ 选择，Enter 恢复，Esc 取消。"""

    BINDINGS = [Binding("escape", "cancel", "取消")]

    DEFAULT_CSS = """
    ResumeScreen {
        align: center middle;
        background: $background 60%;
    }

    #resume-box {
        width: 80%;
        height: 70%;
        border: round $primary;
        background: $surface;
        padding: 0 1;
    }

    #resume-title {
        height: 1;
        padding: 0 1;
        text-style: bold;
        background: $primary;
        color: $text;
    }

    #resume-list {
        height: 1fr;
        margin: 1 0;
    }

    #resume-empty {
        height: auto;
        padding: 1;
        color: $text-muted;
    }
    """

    def __init__(self, sessions: list[SessionSummary]) -> None:
        super().__init__()
        self._sessions = sessions

    def compose(self) -> ComposeResult:
        with Vertical(id="resume-box"):
            yield Static(
                "恢复历史会话 · ↑/↓ 选择 · Enter 恢复 · Esc 取消",
                id="resume-title",
            )
            if self._sessions:
                options = [
                    Option(
                        Text.assemble(
                            (summary.title, "bold"),
                            (f"  {summary.id}", "dim"),
                            (
                                f"  · {summary.message_count} 条消息",
                                "dim",
                            ),
                        ),
                        id=summary.id,
                    )
                    for summary in self._sessions
                ]
                yield OptionList(*options, id="resume-list")
            else:
                yield Static("暂无历史会话", id="resume-empty")

    def on_mount(self) -> None:
        try:
            option_list = self.query_one("#resume-list", OptionList)
        except Exception:
            return
        option_list.focus()
        option_list.highlighted = 0

    def on_option_list_option_selected(
        self,
        event: OptionList.OptionSelected,
    ) -> None:
        self.dismiss(event.option.id)

    def action_cancel(self) -> None:
        self.dismiss(None)


class ConfigNoticeApp(App[None]):
    """配置文件首次生成后的提示对话框。"""

    BINDINGS = [
        Binding("escape", "close", "关闭"),
        Binding("enter", "close", "关闭"),
    ]

    CSS = """
    Screen {
        align: center middle;
        background: $surface;
    }

    #notice-box {
        width: 80;
        height: auto;
        border: round $warning;
        padding: 1 2;
        background: $panel;
    }

    #notice-title {
        text-style: bold;
        color: $warning;
        margin-bottom: 1;
    }

    #notice-close {
        margin-top: 1;
        width: 16;
    }
    """

    def __init__(self, config_path: Path) -> None:
        super().__init__()
        self._config_path = config_path

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(id="notice-box"):
            yield Static("已创建新的配置文件", id="notice-title")
            yield Static(
                Text(
                    f"未找到配置文件，已自动创建：\n{self._config_path}\n\n"
                    "文件内填写的是 mock 信息，请修改 [llm] 中的 "
                    "api_key、base_url、model 后重新启动 xAgent。\n\n"
                    "按 Enter 或 Esc 关闭。"
                )
            )
            yield Button("我知道了", id="notice-close", variant="warning")
        yield Footer()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "notice-close":
            self.exit()

    def action_close(self) -> None:
        self.exit()


class SlashCommandInput(Input):
    """输入框：斜杠命令面板打开时拦截导航键。"""

    async def _on_key(self, event: Any) -> None:
        app = self.app
        if getattr(app, "completion_visible", False) and event.key in {
            "up",
            "down",
            "tab",
            "escape",
        }:
            handled = app.handle_completion_key(event.key)
            if handled:
                event.stop()
                event.prevent_default()
                return
        await super()._on_key(event)

    async def action_submit(self) -> None:
        app = self.app
        if getattr(app, "completion_visible", False):
            highlighted = app.highlighted_completion()
            if highlighted is not None and self.value.strip() == highlighted:
                app.hide_completion()
                await super().action_submit()
                return
            app.accept_completion()
            return
        await super().action_submit()


class FileOpsTuiApp(App[None]):
    TITLE = "XAgent · 文件操作助手"
    SUB_TITLE = "core + tui"
    CSS_PATH = "styles.tcss"
    BINDINGS = [
        Binding("ctrl+q", "quit_app", "退出", priority=True),
        Binding("ctrl+l", "new_session", "新建会话"),
    ]

    def __init__(self, runtime: AgentRuntime) -> None:
        super().__init__()
        self._runtime = runtime
        self._agent = runtime.session
        self._config = runtime.config
        self._store = runtime.session_store
        self._busy = False
        self._warned = False
        self._session_id: str | None = None
        self._session_created_at: str | None = None
        self._mcp_loading = True
        self._mcp_notices: list[str] = []
        self._completion_visible = False
        self._completion_suppressed = False
        self._message_max_chars = self._config.ui.message_max_chars

    @property
    def completion_visible(self) -> bool:
        return self._completion_visible

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal(id="body"):
            with Vertical(id="sidebar"):
                yield Static("MCP 连接", classes="sidebar-title")
                yield VerticalScroll(
                    Static("正在加载 MCP…", id="mcp-list"),
                    id="mcp-scroll",
                )
            with Vertical(id="main"):
                yield VerticalScroll(id="chat")
                yield OptionList(id="completion")
                yield Static("上下文 --", id="context")
                yield Static("就绪", id="status")
                yield SlashCommandInput(
                    placeholder="输入指令或 / 选择命令，回车发送，exit 退出…",
                    id="prompt",
                )
        yield Footer()

    async def on_mount(self) -> None:
        await self._append_message(
            "system",
            "系统",
            "文件操作助手已就绪。输入 / 可查看斜杠命令，输入 /compact 压缩上下文，"
            "输入 exit 退出，Ctrl+L 新建会话。",
        )
        if self._agent.project_context:
            await self._append_message(
                "system",
                "项目上下文",
                "已加载项目 AGENTS.md，并在本会话中复用。",
            )
        self._set_status("就绪 · 输入 exit 退出")
        self._refresh_context()
        await self._persist_initial_project_context()
        self.query_one("#prompt", Input).focus()
        self.run_worker(self._load_mcp(), group="mcp", exclusive=True)

    async def _persist_initial_project_context(self) -> None:
        """首次加载时把 AGENTS.md 注入内容写入会话事件日志。"""

        if not self._agent.project_context or self._session_id is not None:
            return
        try:
            summary = self._store.save(self._agent.history)
        except OSError as exc:
            self.notify(f"保存初始会话失败: {exc}", severity="error")
            return
        self._session_id = summary.id
        self._session_created_at = summary.created_at

    async def _load_mcp(self) -> None:
        result = await load_mcp_async(
            self._agent.tools,
            self._agent.workspace,
            self._config.mcp,
        )
        if result.manager is not None:
            self._agent.set_mcp_manager(result.manager)
        self._mcp_notices = result.notices
        self._mcp_loading = False
        self._refresh_mcp()
        self._refresh_context()
        if result.notices:
            self.notify(
                "；".join(result.notices),
                title="MCP 加载结果",
                timeout=8,
            )

    def _refresh_mcp(self) -> None:
        lines: list[Text] = []
        if self._mcp_loading:
            lines.append(Text("正在加载 MCP…", style="yellow"))
        else:
            servers = describe_manager(self._agent.mcp_manager)
            if not servers:
                lines.append(Text("未连接 MCP Server", style="dim"))
            for server in servers:
                status = server["status"]
                if status == "connected":
                    lines.append(
                        Text.assemble(
                            ("● ", "green"),
                            (server["name"], "bold green"),
                            ("  已连接", "green"),
                        )
                    )
                elif status == "error":
                    lines.append(
                        Text.assemble(
                            ("● ", "red"),
                            (server["name"], "bold red"),
                            ("  失败", "red"),
                        )
                    )
                    if server["detail"]:
                        lines.append(
                            Text(f"    {server['detail']}", style="red dim")
                        )
                else:
                    lines.append(
                        Text.assemble(
                            ("● ", "yellow"),
                            (server["name"], "yellow"),
                            ("  连接中", "yellow"),
                        )
                    )
                for tool_name in server["tools"]:
                    lines.append(Text(f"    - {tool_name}", style="dim"))
            for notice in self._mcp_notices:
                lines.append(Text(notice, style="dim"))
        if not lines:
            lines.append(Text("未连接 MCP Server", style="dim"))
        self.query_one("#mcp-list", Static).update(Text("\n").join(lines))

    async def on_input_changed(self, event: Input.Changed) -> None:
        self._update_completion(event.value)

    def _update_completion(self, value: str) -> None:
        if self._completion_suppressed:
            self._completion_suppressed = False
            self._hide_completion()
            return
        text = value.strip()
        if not text.startswith("/") or any(char.isspace() for char in text):
            self._hide_completion()
            return
        keyword = text[1:].lower()
        matches = [
            (command, description)
            for command, description in SLASH_COMMANDS
            if command[1:].lower().startswith(keyword)
        ]
        if not matches:
            self._hide_completion()
            return
        option_list = self.query_one("#completion", OptionList)
        option_list.clear_options()
        option_list.add_options(
            [
                Option(
                    Text.assemble(
                        (command, "bold"),
                        ("  ", ""),
                        (description, "dim"),
                    ),
                    id=command,
                )
                for command, description in matches
            ]
        )
        option_list.highlighted = 0
        option_list.styles.display = "block"
        self._completion_visible = True

    def _hide_completion(self) -> None:
        if not self._completion_visible:
            return
        self._completion_visible = False
        self.query_one("#completion", OptionList).styles.display = "none"

    def handle_completion_key(self, key: str) -> bool:
        if not self._completion_visible:
            return False
        option_list = self.query_one("#completion", OptionList)
        if key == "escape":
            self._hide_completion()
            return True
        if key in {"enter", "tab"}:
            self.accept_completion()
            return True
        count = option_list.option_count
        if count == 0:
            return False
        current = option_list.highlighted or 0
        if key == "up":
            option_list.highlighted = (current - 1) % count
        elif key == "down":
            option_list.highlighted = (current + 1) % count
        else:
            return False
        return True

    def highlighted_completion(self) -> str | None:
        if not self._completion_visible:
            return None
        option_list = self.query_one("#completion", OptionList)
        index = option_list.highlighted
        if index is None or index >= option_list.option_count:
            return None
        option = option_list.get_option_at_index(index)
        return option.id

    def hide_completion(self) -> None:
        self._hide_completion()

    def accept_completion(self) -> None:
        option_list = self.query_one("#completion", OptionList)
        index = option_list.highlighted
        if index is None or index >= option_list.option_count:
            self._hide_completion()
            return
        option = option_list.get_option_at_index(index)
        if option.id is None:
            self._hide_completion()
            return
        self._completion_suppressed = True
        prompt = self.query_one("#prompt", SlashCommandInput)
        prompt.value = option.id
        prompt.cursor_position = len(option.id)
        prompt.focus()
        self._hide_completion()

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        text = event.value.strip()
        event.input.value = ""
        self._hide_completion()

        if not text:
            return
        if text.lower() in {"exit", "quit", "/exit", "/quit"}:
            await self._quit()
            return
        if text.startswith("/"):
            await self._dispatch_command(text)
            return
        if self._busy:
            self.notify("正在处理上一条消息，请稍候", severity="warning")
            return
        if self._agent.needs_compaction():
            usage = self._agent.context_usage()
            self.notify(
                f"上下文已占用 {usage.ratio * 100:.1f}%，"
                "请先执行 /compact 压缩上下文",
                severity="warning",
                timeout=10,
            )
            return

        self._busy = True
        event.input.disabled = True
        self._set_status("思考中…")
        self.run_worker(self._run_turn(text), group="agent", exclusive=True)

    async def _dispatch_command(self, text: str) -> None:
        command = text.split(maxsplit=1)[0].lower()
        if command == "/compact":
            if self._busy:
                self.notify("正在处理上一条消息，请稍候", severity="warning")
                return
            self._busy = True
            prompt = self.query_one("#prompt", SlashCommandInput)
            prompt.disabled = True
            self._set_status("正在压缩上下文…")
            self.run_worker(self._run_compact(), group="agent", exclusive=True)
            return
        if command == "/resume":
            if self._busy:
                self.notify("正在处理上一条消息，请稍候", severity="warning")
                return
            self._busy = True
            prompt = self.query_one("#prompt", SlashCommandInput)
            prompt.disabled = True
            self.run_worker(self._run_resume(), group="agent", exclusive=True)
            return
        if command == "/help":
            await self._show_help()
        elif command == "/new":
            await self._new_session()
        elif command == "/save":
            await self._save_current(show_message=True)
        elif command == "/status":
            await self._show_status()
        elif command == "/mcp":
            self._refresh_mcp()
            await self._show_status()
        elif command in {"/quit", "/exit"}:
            await self._quit()
        else:
            self.notify(f"未知命令: {command}，输入 /help 查看可用命令", severity="warning")

    async def _show_help(self) -> None:
        lines = ["可用斜杠命令："]
        for command, description in SLASH_COMMANDS:
            lines.append(f"  {command:<10} {description}")
        lines.append("")
        lines.append("输入 / 会弹出补全引导面板，↑/↓ 选择，Enter 补全。")
        await self._append_message("system", "帮助", "\n".join(lines))

    async def _show_status(self) -> None:
        usage = self._agent.context_usage()
        default_tag = "（默认）" if usage.window_is_default else ""
        servers = describe_manager(self._agent.mcp_manager)
        lines = [
            f"会话编号: {self._session_id or '（尚未保存）'}",
            f"历史消息: {len(self._agent.history)} 条",
            (
                f"上下文: {_format_k(usage.tokens)} / "
                f"{_format_k(usage.window)} "
                f"({usage.ratio * 100:.1f}%){default_tag}"
            ),
            f"MCP Server: {len(servers)} 个",
        ]
        for server in servers:
            tools = ", ".join(server["tools"]) or "（无工具）"
            lines.append(f"  - {server['name']} [{server['status']}]: {tools}")
        await self._append_message("system", "状态", "\n".join(lines))

    async def _new_session(self) -> None:
        if self._busy:
            self.notify("请等待当前任务完成后再新建会话", severity="warning")
            return
        await self._save_current(show_message=False)
        self._session_id = None
        self._session_created_at = None
        self._agent.reset()
        self._warned = False
        chat = self.query_one("#chat", VerticalScroll)
        await chat.remove_children()
        await self._append_message(
            "system",
            "系统",
            "已新建会话。",
        )
        self._refresh_context()
        self.query_one("#prompt", SlashCommandInput).focus()

    async def _save_current(self, *, show_message: bool) -> None:
        try:
            summary = self._store.save(
                self._agent.history,
                session_id=self._session_id,
                created_at=self._session_created_at,
            )
        except OSError as exc:
            self.notify(f"保存会话失败: {exc}", severity="error")
            return
        self._session_id = summary.id
        self._session_created_at = summary.created_at
        if show_message:
            await self._append_message(
                "system",
                "会话",
                f"已保存会话 {summary.id}（{summary.message_count} 条消息）。",
            )
        else:
            self.notify(f"会话已保存: {summary.id}", timeout=4)

    async def _quit(self) -> None:
        if not self._busy and self._agent.has_conversation():
            await self._save_current(show_message=False)
        self.exit()

    async def action_quit_app(self) -> None:
        await self._quit()

    async def action_new_session(self) -> None:
        await self._new_session()

    async def _run_turn(self, text: str) -> None:
        try:
            async for event in self._agent.send(text):
                await self._render_event(event)
                if event.type is AgentEventType.TOOL_CALL:
                    self._set_status(f"正在执行工具: {event.tool_name}…")
                elif event.type is AgentEventType.ASSISTANT_MESSAGE:
                    self._set_status("整理回复…")
        except Exception as exc:
            await self._append_message("error", "错误", f"会话执行失败: {exc}")
        finally:
            self._finish_busy()

    async def _run_compact(self) -> None:
        try:
            async for event in self._agent.compact():
                await self._render_event(event)
        except Exception as exc:
            await self._append_message("error", "错误", f"上下文压缩失败: {exc}")
        finally:
            if self._agent.has_conversation():
                await self._save_current(show_message=False)
            self._finish_busy()

    async def _run_resume(self) -> None:
        try:
            summaries = self._store.list()
            if not summaries:
                self.notify("暂无历史会话", severity="warning")
                return
            selected = await self.push_screen_wait(ResumeScreen(summaries))
            if not selected:
                return
            messages = self._store.load(selected)
            if messages is None:
                self.notify("会话文件读取失败", severity="error")
                return
            if self._agent.has_conversation():
                await self._save_current(show_message=False)
            self._agent.load_history(messages)
            self._session_id = selected
            self._session_created_at = next(
                (item.created_at for item in summaries if item.id == selected),
                None,
            )
            self._warned = False
            await self._render_history(self._agent.history)
            await self._append_message(
                "system",
                "会话",
                f"已恢复会话 {selected}。",
            )
            self._refresh_context()
        except Exception as exc:
            await self._append_message("error", "错误", f"恢复会话失败: {exc}")
        finally:
            self._finish_busy()

    def _finish_busy(self) -> None:
        self._busy = False
        prompt = self.query_one("#prompt", SlashCommandInput)
        prompt.disabled = False
        prompt.focus()
        self._refresh_context()
        self._set_status("就绪 · 输入 exit 退出")

    async def _render_history(self, messages: list[dict[str, Any]]) -> None:
        chat = self.query_one("#chat", VerticalScroll)
        await chat.remove_children()
        for index, message in enumerate(messages):
            role = message.get("role")
            content = message.get("content") or ""
            if role == "system":
                if index == 0:
                    continue
                await self._append_message("system", "系统", str(content))
            elif role == "user":
                if str(content).startswith(PROJECT_CONTEXT_PREFIX):
                    await self._append_message(
                        "system", "项目上下文", "已加载 AGENTS.md"
                    )
                else:
                    await self._append_message("user", "你", str(content))
            elif role == "assistant":
                body = str(content or "").strip()
                tool_calls = message.get("tool_calls") or []
                if body:
                    await self._append_message("assistant", "AI", body)
                elif tool_calls:
                    names = ", ".join(
                        str(call.get("function", {}).get("name", "tool"))
                        for call in tool_calls
                        if isinstance(call, dict)
                    )
                    await self._append_message(
                        "tool", "历史工具调用", names or "（无名称）"
                    )
            elif role == "tool":
                await self._append_message(
                    "result",
                    "历史工具结果",
                    _format_tool_result(str(content), self._message_max_chars),
                )

    async def _render_event(self, event: AgentEvent) -> None:
        if event.type is AgentEventType.USER_MESSAGE:
            await self._append_message("user", "你", event.text or "")
        elif event.type is AgentEventType.TOOL_CALL:
            await self._append_message(
                "tool",
                f"调用工具 · {event.tool_name}",
                _format_json(
                    event.tool_arguments or {},
                    max_chars=self._message_max_chars,
                ),
            )
        elif event.type is AgentEventType.TOOL_RESULT:
            await self._append_message(
                "result",
                f"工具结果 · {event.tool_name}",
                _format_tool_result(
                    event.tool_result or "",
                    self._message_max_chars,
                ),
            )
        elif event.type is AgentEventType.ASSISTANT_MESSAGE:
            await self._append_message(
                "assistant",
                "AI",
                event.text or "（模型未返回文本）",
            )
        elif event.type is AgentEventType.ERROR:
            await self._append_message("error", "错误", event.text or "未知错误")
        elif event.type is AgentEventType.CONTEXT_STATE:
            self._refresh_context()
        elif event.type is AgentEventType.COMPACTION_STARTED:
            await self._append_message(
                "system", "上下文压缩", event.text or "开始压缩上下文…"
            )
        elif event.type is AgentEventType.COMPACTION_FINISHED:
            await self._append_message(
                "system", "上下文压缩", event.text or "上下文压缩完成"
            )
            self.push_screen(
                CompactionScreen(
                    event.compaction_before or "",
                    event.compaction_after or "",
                )
            )

    async def _append_message(self, role: str, title: str, body: str) -> None:
        chat = self.query_one("#chat", VerticalScroll)
        await chat.mount(ChatMessage(role, title, body))
        chat.scroll_end(animate=False)

    def _refresh_context(self) -> None:
        usage = self._agent.context_usage()
        default_tag = "（默认）" if usage.window_is_default else ""
        text = (
            f"上下文 {_format_k(usage.tokens)} / {_format_k(usage.window)}"
            f"   已占用 {usage.ratio * 100:.1f}%{default_tag}"
        )
        warning_ratio = self._config.context.warning_ratio
        if usage.ratio >= 0.8:
            style = "bold red"
        elif usage.ratio >= warning_ratio:
            style = "bold yellow"
        else:
            style = "green"
        self.query_one("#context", Static).update(Text(text, style=style))

        if usage.ratio >= warning_ratio:
            if not self._warned:
                self._warned = True
                self.notify(
                    f"上下文已占用 {usage.ratio * 100:.1f}%，"
                    "请执行 /compact 压缩上下文",
                    severity="warning",
                    timeout=10,
                )
        else:
            self._warned = False

    def _set_status(self, text: str) -> None:
        self.query_one("#status", Static).update(Text(text))
