# 幕僚plus

**把问题想清楚，再决定下一步。**

李拜日整理的综合思考 Skill。面对人生选择、工作处境或一个新的想法，把事实与猜测分开，看见遗漏的选项，也保留自己的判断。

![幕僚plus](docs/assets/avatar.png)

这是可以安装到支持 Agent Skills 的工具中的独立 Skill。免费使用，不需要作者提供 API Key。模型运行使用安装者自己的账号与额度。

## 能帮你做什么

- 人生与工作选择。比较现实选项，讲清代价，把你重视的生活与责任放进判断。
- 商业与产品想法。核对关键前提，用可承受的尝试获得真实反馈。
- 内容与个人困惑。换角度理解问题，按需要讨论想法或形成下一步。

内置10种可跨领域使用的方法，按问题逐步加载。简单问题直接回答，不要求每次走完全部流程。

## 安装到 Codex

把下面这段话发给 Codex。

> 请用 skill-installer 从 https://github.com/libairi/mouliao-plus 安装 skills/mouliao-plus 这个 Skill。先核对已有同名 Skill，保留我的其他配置，不覆盖不同来源的版本。安装后确认入口可以被发现，并告诉我怎么调用。

安装后可以输入 `$mouliao-plus`。若新 Skill 没出现，重启 Codex 或开一个新聊天再看。

也可以从本仓库下载 ZIP，解压后把 `skills/mouliao-plus` 整个文件夹放到当前 Codex 支持的个人 Skill 目录。现行手动目录是 `~/.agents/skills/`，系统 skill-installer 也可能使用 `~/.codex/skills/`；以本机安装工具和官方文档为准，保留 `references/`、`scripts/` 与 `agents/` 子目录。

## 安装到 Claude Code 或其他 Agent

Claude Code 用户可把 `skills/mouliao-plus` 复制到 `~/.claude/skills/mouliao-plus`，或项目的 `.claude/skills/mouliao-plus`，然后使用 `/mouliao-plus`。

其他 Agent 按其 Agent Skills 安装方式导入同一目录。各产品支持的工具和安装位置不同，未逐一实测；支持读取 Skill 不代表一定能执行可选脚本。

## 从一个真实问题开始

> 我很羡慕朋友升职，但真的不想管理团队。我只想理清自己羡慕什么，先别给行动计划。

> 我想做内容，但又担心影响主业。请先帮我比较现实选项，找出最值得验证的未知点。

这些是使用示例，不代表真实用户评价。

## 可选资料查证

基本咨询不需要 Python，也不需要资料库。若希望查证自己的本地材料，需要 Agent 能访问文件并执行脚本，再按 `references/local-library.md` 配置你自己的目录。

可选脚本需要 Python 3.10或以上；EPUB使用标准库，PDF文字提取额外需要PyMuPDF。扫描文件和暂不支持的格式不会被当作已读原文。你的原件保持只读，派生索引由你自己管理。

## 内容与隐私

公开版包含核心提示词与可执行的方法说明，不包含发布者的私有书目、资料原文、出处映射、全文索引或私人配置。它不访问发布者电脑，也没有发布者运营的远程模型服务。

公开文件中的提示词与方法可以直接阅读。引用用户自己提供的材料时，应实际核对；缺少材料时不编造引文、页码或已读状态。聊天与工具输出仍由你使用的平台按其政策处理。

你可以随时停止使用。Skill不替你作重大决定，不保证结果，也不承诺永久记忆。

## 图文介绍

保留了独立的图文介绍页。下载仓库后，双击 `docs/index.html` 可在本机查看，样式和图片无需单独联网加载。仓库中的支持、隐私与使用说明也可以从页面底部打开。

## 更新

当前版本为1.0.1。收到新版本后，请先核对本机安装位置与自己的改动，再更新同一个Skill目录。首次文件检查与本机功能验证不代表已经测试所有Agent平台。

安装依据见 [Codex官方说明](https://learn.chatgpt.com/docs/build-skills)、[Claude Code官方说明](https://code.claude.com/docs/en/skills)和[Agent Skills格式规范](https://agentskills.io/specification)。
