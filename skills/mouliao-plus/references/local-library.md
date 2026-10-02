# 可选的本地资料查询

基本分析不依赖本地书库。用户提供书库工作区且宿主能读文件、执行 Python 时，才使用以下流程。不要寻找Skill作者的电脑目录，不上传原书或索引。

先检查用户工作区的 config/sources.json 与 library/catalog.json。若目录不存在且未设置 MOULIAO_WORKSPACE，使用方法摘要和用户材料，说明未查询原文。用户要求原文查证时，再询问可访问的书或工作区。

以下 SCRIPT 指本 Skill 文件夹下的 scripts/library.py；WORKSPACE 是用户已给出的工作区。

```sh
python3 "$SCRIPT" --workspace "$WORKSPACE" status
python3 "$SCRIPT" --workspace "$WORKSPACE" books '用户提供的书名'
python3 "$SCRIPT" --workspace "$WORKSPACE" search '调查' '事实' --book '用户提供的书名' --limit 5
python3 "$SCRIPT" --workspace "$WORKSPACE" read '检索返回的片段ID' --whole-unit --max-chars 10000
```

检索是关键词匹配。把问题改写成少量具体词，必要时换同义词。命中用于定位；引用前回读上下文，检查 truncated 与 freshness，片段不足时用 --offset 继续读。引用书名、章节和短语；PDF 的页数明确为文件页，不称作纸书印刷页。

text_indexed 代表文字已提取；partial_text_needs_ocr 代表部分可查；needs_ocr_or_access 与 catalog_only 没有可供本工具查证的正文。文字提取不等于精读；未命中不证明原书没有这个观点。

来源变化或删除时不把旧索引当新证据。用户授权维护书库后，才运行 build 重建派生索引。源书保持只读。

```sh
python3 "$SCRIPT" --workspace "$WORKSPACE" build
```

## 首次配置用户自己的资料

基本咨询不需要建库。用户明确要求接入其资料时，在用户指定的独立工作区创建config/sources.json，登记其实际授权的目录。sources列表中每项有id、label、path和read_only字段；index_directory设为library。用真实目录替换下例占位文本后再执行，不能把发布者的工作区当成默认资料。

```json
{"sources":[{"id":"my-books","label":"我的资料","path":"用户授权的资料目录绝对路径","read_only":true}],"index_directory":"library"}
```

本地检索需要Python 3.10或以上。EPUB处理只用标准库；PDF文字提取额外需要PyMuPDF。缺依赖时说明现状，得到用户安装许可后再处理。MOBI、AZW3及无可提取文字的扫描文件不充当已读正文。运行脚本时始终显式传入--workspace。
