# STIL to NI-Digital 中文使用手册

本文档适用于 `STIL to NI-Digital v0.2.1`。软件用于将常见的、面向扫描测试的 Synopsys TetraMAX STIL 文件转换为 NI Digital Pattern Editor / NI PXI Digital Pattern Instrument 可继续处理的文件。

> [!IMPORTANT]
> 本工具不是完整的 IEEE 1450 STIL 解析器。它只转换项目明确支持的 STIL 子集；遇到无法可靠转换的结构时会停止并报错，不会故意静默改变测试语义。

## 1. 软件能做什么

输入文件：

- `.stil`
- `.stil.gz`，即 gzip 压缩的 STIL 文件

主要输出：

- `.digipatsrc`：NI 可读、可编辑的数字 Pattern 源文件。
- `.digitiming`：NI Timing Sheet，包含周期、驱动边沿和比较采样点。
- `.pinmap`：逻辑 Pin Map，包含 DUT 引脚和 `AllPins` 引脚组。
- `conversion_report.txt`：转换摘要、周期数、扫描链信息及输出文件 SHA-256。
- `.digipat`：可选。仅当电脑中安装并检测到 NI Digital Pattern Compiler 时生成。

转换在本机完成，程序不会上传 STIL 文件或转换结果。

## 2. 下载与首次启动

### 2.1 下载 Windows 版

从项目的 [最新发布页面](https://github.com/dong7727/stil-to-ni-digital/releases/latest) 下载：

```text
STIL-to-NI-Digital.exe
SHA256SUMS.txt
```

独立 EXE 已包含运行所需的 Python 和 Qt 组件，不需要另外安装 Python。

### 2.2 校验下载文件

在 EXE 所在目录打开 PowerShell，执行：

```powershell
Get-FileHash .\STIL-to-NI-Digital.exe -Algorithm SHA256
```

v0.2.1 的正确 SHA-256 为：

```text
926996F8DE7DAA635566451006A1947E26F7C090E823E083819E0127647249A2
```

计算结果也应与同一 Release 中的 `SHA256SUMS.txt` 一致。其他版本必须以对应 Release 附带的校验文件为准。

### 2.3 Windows SmartScreen 提示

当前 EXE 未购买商业代码签名证书，因此 Windows SmartScreen 可能显示“Windows 已保护你的电脑”。确认下载来源和 SHA-256 正确后，可选择：

1. 点击“更多信息”。
2. 核对应用名称。
3. 点击“仍要运行”。

如果公司电脑由 IT 策略禁止运行未签名程序，请使用后文的 Python 命令行安装方式，或让 IT 部门审核后加入允许列表。

## 3. 图形界面快速开始

### 3.1 选择输入文件

可使用以下任一方式：

- 双击 `STIL-to-NI-Digital.exe`，点击“浏览…”选择文件。
- 将 `.stil` 或 `.stil.gz` 文件拖到程序窗口中的虚线区域。
- 将 STIL 文件直接拖到 EXE 图标上，程序启动后会自动填入该文件。

选择输入文件后，软件默认把输出目录设置为输入文件旁边的：

```text
<STIL文件名>_NI_Output
```

例如：

```text
D:\patterns\device_scan.stil
```

对应的默认输出目录为：

```text
D:\patterns\device_scan_NI_Output
```

### 3.2 选择输出目录

可以直接使用自动建议的目录，也可以点击“输出目录…”选择其他文件夹。

如果目录不存在，程序会自动创建。如果目录已经包含文件，程序会提示确认；继续后，同名结果文件会被覆盖，其他不同名文件不会被删除。

建议每个 STIL 文件使用独立的空目录，便于核对结果和保存转换记录。

### 3.3 设置转换选项

#### 完全展开扫描周期

此选项默认勾选，作用是额外生成：

```text
<文件名>.expanded.digipatsrc
```

展开文件把 `scan(n)` 块转换成普通 vector，每个测试周期对应一条 vector 语句。适合以下情况：

- 要求 Pattern 全部为单行 vector。
- 下游流程不能处理 `scan()` 块。
- 需要逐周期查看、比较或修改扫描数据。

勾选后仍会同时保留紧凑版 `.digipatsrc`，不会只生成展开版。

需要注意：长扫描链会使展开文件非常大。若输入包含数百万个周期，转换时间、磁盘占用和 NI 编辑器打开时间都会明显增加。不需要逐周期展开时，可取消勾选并使用紧凑版。

#### 调用 NI Digital Pattern Compiler

当程序检测到 NI Digital Pattern Compiler 时，此选项可以勾选。转换完成后会继续编译：

- `<文件名>.digipatsrc` → `<文件名>.digipat`
- `<文件名>.expanded.digipatsrc` → `<文件名>.expanded.digipat`，仅在生成展开版时执行

如果此选项呈灰色，表示程序没有在系统 `PATH` 或常见 NI 安装目录中找到 `DigitalPatternCompiler.exe`。这不影响生成 `.digipatsrc`、`.digitiming` 和 `.pinmap`。

### 3.4 开始转换

点击“开始转换”后：

1. 程序检查输入文件和输出目录。
2. 解析 STIL 中的引脚、SignalGroups、WaveformTables、ScanStructures、Procedures、MacroDefs 和 Pattern。
3. 计算并核对测试周期数。
4. 生成 NI Pattern Source、Timing、Pin Map 和转换报告。
5. 如果勾选完全展开，逐周期生成展开版 Pattern。
6. 如果勾选 NI 编译，再调用 NI 编译器生成 `.digipat`。

转换期间界面会显示运行状态和日志。为了防止输出文件只写入一部分，转换结束前程序不会允许直接关闭窗口。

### 3.5 查看结果

成功后会弹出“转换完成”，其中包含：

- 测试周期总数
- 输出目录

点击“打开输出目录”即可查看生成文件。日志区域同时显示每个输出文件的完整路径和 NI 编译器输出。

## 4. 输出文件详解

假设输入文件为：

```text
device_scan.stil
```

并勾选“完全展开扫描周期”，输出目录通常包含：

| 文件 | 用途 |
| --- | --- |
| `device_scan.digipatsrc` | 紧凑 Pattern 源文件，扫描数据保留为 `scan(n)` 块。 |
| `device_scan.expanded.digipatsrc` | 展开 Pattern 源文件，每个测试周期是一条普通 vector。 |
| `device_scan.digitiming` | Timing Sheet，记录 timeset、周期和各引脚边沿。 |
| `device_scan.pinmap` | 逻辑 Pin Map，仅定义 DUT 引脚和 `AllPins` 引脚组。 |
| `conversion_report.txt` | 输入哈希、引脚方向、扫描链、周期数和输出哈希。 |
| `device_scan.digipat` | 可选，NI 编译器生成的紧凑版二进制 Pattern。 |
| `device_scan.expanded.digipat` | 可选，NI 编译器生成的展开版二进制 Pattern。 |

### 4.1 紧凑版和展开版如何选择

| 使用场景 | 建议文件 |
| --- | --- |
| 节省空间、保留扫描结构 | `device_scan.digipatsrc` |
| 要求全是单行 Pattern | `device_scan.expanded.digipatsrc` |
| 逐周期检查 Scan In / Scan Out | `device_scan.expanded.digipatsrc` |
| NI 编译和执行 | 对选定的源文件生成对应 `.digipat` |

两种源文件表达的测试周期总数应相同。转换器会在写出展开文件后再次核对周期数；不一致时会停止并报告错误。

### 4.2 `.digitiming` 包含什么

转换器根据 STIL WaveformTable 生成 NI timeset：

- 普通输入驱动使用 `DriveNonReturn`。
- STIL `P` 波形的 `D/U/D` 转换为 `ReturnToLow`。
- STIL `P` 波形的 `U/D/U` 转换为 `ReturnToHigh`。
- 输出比较使用 `CompareStrobe`。

STIL 中同一个 waveform character 可能在不同引脚上代表不同边沿行为，因此转换器会按需创建专用 timeset，而不是把所有 `P` 简单替换成一个固定的 NI 符号。

### 4.3 `.pinmap` 不包含什么

生成的 Pin Map 是逻辑模板，不包含测试站特有信息：

- PXI 机箱和仪器资源名
- Site 数量
- NI 数字仪器通道号
- DUT 引脚到仪器通道的 Connection
- 负载板和治具接线

这些信息必须根据实际测试站在 NI Digital Pattern Editor、TestStand Semiconductor Module 或相应 API 配置中补充。

### 4.4 `conversion_report.txt` 的用途

建议每次转换都保留此文件。它包含：

- 输入 STIL 的完整路径和 SHA-256
- 引脚名称及方向
- WaveformTable 列表
- Scan In、Scan Out 和扫描链长度
- 生成周期数及源文件声明的周期数
- NI vector / scan 指令数量
- 每个输出文件的大小和 SHA-256

该报告适合用于版本追溯、转换结果复核和生产发布记录。

## 5. 在 NI 环境中使用输出

转换完成不代表 Pattern 已经可以直接上机。推荐流程如下：

1. 在 NI Digital Pattern Editor 中检查或导入生成的 `.pinmap`。
2. 根据测试站补充 Instrument、Site、Channel 和 Connection。
3. 检查 `.digitiming` 中的周期、驱动边沿、Return 边沿和 Compare Strobe。
4. 单独创建或配置适用于器件的电压电平；本工具不生成 `.digilevels`。
5. 打开或编译选定的 `.digipatsrc`。
6. 在 Pattern 编辑器中检查引脚顺序、timeset 名称、scan 长度和 halt 位置。
7. 先使用仿真、已知良好向量或 golden device 验证。
8. 首次连接硬件时设置安全的电压、电流、频率和超时限制。
9. 验证通过后，再集成到 TestStand 或生产测试流程。

不同 NI 软件版本的菜单名称可能不同，以上描述的是文件关系和验证顺序，不依赖某个特定版本的菜单路径。

## 6. 生产使用前检查清单

### 输入与转换

- [ ] 输入文件来自受控版本，SHA-256 已记录。
- [ ] STIL 文件为 UTF-8 文本；压缩文件为有效 gzip。
- [ ] 转换日志没有报错或周期不一致。
- [ ] `conversion_report.txt` 中的 Source-reported cycles 与 Generated cycles 一致，或已确认源文件没有周期摘要。
- [ ] Scan In、Scan Out 和扫描链长度与 ATPG 配置一致。
- [ ] 展开版的用途明确，文件大小和磁盘空间可接受。

### NI 配置

- [ ] 引脚名称、方向和顺序与 DUT/负载板一致。
- [ ] 每个 DUT 引脚均连接到正确的 NI 通道和 Site。
- [ ] timeset 周期和所有边沿已对照 STIL 检查。
- [ ] ReturnToLow / ReturnToHigh 极性已检查。
- [ ] Compare Strobe 位于信号稳定窗口。
- [ ] 电压、电流、终端和负载配置已单独完成。

### 验证与发布

- [ ] Pattern 已通过 NI 编译器。
- [ ] 已使用仿真、golden vectors 或 golden device 验证。
- [ ] 已验证 pass、fail、timeout、abort 和 cleanup 路径。
- [ ] 首次上机采用安全限制和较低风险条件。
- [ ] 已归档 STIL、转换器版本、转换报告和最终 NI 文件的校验值。

## 7. 常见问题与处理方法

### 7.1 EXE 无法启动

处理顺序：

1. 确认下载的是 v0.2.1 或更高版本；v0.2.0 在部分中文路径下可能无法启动。
2. 重新计算 SHA-256，确认文件完整。
3. 将 EXE 放到有读写权限的普通目录，例如 `D:\Tools\STIL-to-NI`。
4. 查看 Windows SmartScreen 或杀毒软件是否拦截。
5. 若公司策略禁止未签名 EXE，改用 Python 安装方式。

### 7.2 拖入文件后没有反应

请检查：

- 文件扩展名是否为 `.stil` 或 `.stil.gz`。
- 文件是否真实存在且当前账户有读取权限。
- 不要从某些以管理员身份运行的程序向普通权限窗口拖放；可改用“浏览…”。

### 7.3 “调用 NI Digital Pattern Compiler”呈灰色

原因是没有检测到 `DigitalPatternCompiler.exe`。可采取以下方法：

- 安装 NI Digital Pattern Editor / Digital Pattern Compiler。
- 确认 NI 安装完整且编译器位于常见安装目录。
- 把编译器目录加入系统 `PATH`。
- 使用命令行的 `--compiler` 参数显式指定路径。

### 7.4 转换很慢或展开文件过大

长扫描链乘以大量 Pattern 会产生数百万甚至更多 vector。取消勾选“完全展开扫描周期”，只生成紧凑的 `scan(n)` 版本，可以显著减小文件。

如果下游必须使用展开版，请预留足够磁盘空间，并避免把输出放在同步盘或网络盘上。

### 7.5 提示输出目录非空

程序检测到目录中已有文件。同名结果会被覆盖。若目录中包含需要保留的旧版本，请选择“否”，然后换一个新目录。

### 7.6 提示生成周期数与 STIL 摘要不一致

这是一项安全检查，说明转换器计算出的周期数与 TetraMAX 摘要不一致。不要忽略并直接上机。请检查：

- STIL 是否使用了当前版本不支持的控制结构。
- 文件是否被截断或手工修改。
- Procedure、Macro、Call 或 Shift 是否采用了未支持的写法。

可在 GitHub Issues 中提交一个不含机密信息的最小复现 STIL。

### 7.7 NI 编译器报错

日志会显示 NI 编译器的退出码和输出。优先检查：

- NI 编译器版本是否支持生成的文件格式。
- `.pinmap` 是否被手工修改成无效 XML。
- Pattern 中的引脚名是否与 Pin Map 一致。
- 输出目录是否有写权限。
- 是否正在被其他软件占用同名 `.digipat`。

### 7.8 Pattern 已转换，但不能直接在硬件运行

这是预期情况。生成的 `.pinmap` 只有逻辑引脚，且工具不生成电压电平。必须补充测试站资源、通道映射、Site、Connection 和器件电平，然后完成编译与硬件验证。

## 8. 当前支持的 STIL 子集

v0.2.1 支持：

- `Signals` 中的标量 `In`、`Out` 和 `InOut` 引脚
- 使用 `+` 连接的有序 `SignalGroups`
- 数值型纳秒周期和边沿时间
- 静态 `0`、`1`、`H`、`L`、`X`、`Z` 和 `N`
- 三边沿 `P` 波形：`D/U/D` 和 `U/D/U`
- 一条 `ScanChain`
- `Procedures`、`MacroDefs`、`W`、`C`、`V`、`Call`、`Macro` 和 `Shift`
- TetraMAX `#` 参数替换
- 可选的 TetraMAX 周期摘要校验

当前不支持：

- 多条扫描链
- STIL domains 和 selectors
- loop、goto/match loop 及任意控制流
- 嵌套 `Shift`
- 在 `Signals` 中直接声明的多位 bus
- compare symbol `T`
- 非纳秒单位或公式形式的 timing 表达式
- 自动生成电压电平
- 自动分配 PXI 物理通道

如果文件使用不支持的结构，转换器通常会明确报错，而不是猜测转换方式。

## 9. 命令行使用方法

命令行适合批量转换、自动化和显式指定 NI 编译器。

### 9.1 安装

需要 Python 3.10 或更高版本。在项目目录执行：

```powershell
python -m pip install .
```

开发模式安装：

```powershell
python -m pip install -e .
```

如需同时安装图形界面依赖：

```powershell
python -m pip install ".[gui]"
```

### 9.2 基本转换

生成紧凑 Pattern、Timing、Pin Map 和报告：

```powershell
stil-to-ni "D:\patterns\device_scan.stil" -o "D:\patterns\output"
```

### 9.3 生成全展开 Pattern

```powershell
stil-to-ni "D:\patterns\device_scan.stil" `
  -o "D:\patterns\output" `
  --expand-scan
```

### 9.4 同时编译 `.digipat`

自动查找 NI 编译器：

```powershell
stil-to-ni "D:\patterns\device_scan.stil" `
  -o "D:\patterns\output" `
  --expand-scan `
  --compile
```

显式指定编译器：

```powershell
stil-to-ni "D:\patterns\device_scan.stil" `
  -o "D:\patterns\output" `
  --compile `
  --compiler "C:\Program Files\National Instruments\Digital Pattern Compiler\DigitalPatternCompiler.exe"
```

### 9.5 其他参数

```text
--expand-scan     额外生成每周期一条 vector 的展开版
--no-labels       不在输出 Pattern 中保留 STIL Call 标签
--compile         调用 NI 编译器生成 .digipat
--compiler PATH   显式指定 DigitalPatternCompiler.exe
--version         显示版本号
```

查看完整帮助：

```powershell
stil-to-ni --help
```

## 10. 批量转换示例

以下 PowerShell 示例转换目录下所有 `.stil` 文件，每个文件使用独立输出目录：

```powershell
Get-ChildItem -LiteralPath "D:\patterns" -Filter "*.stil" | ForEach-Object {
    $outputDirectory = Join-Path $_.DirectoryName ($_.BaseName + "_NI_Output")
    stil-to-ni $_.FullName -o $outputDirectory --expand-scan
}
```

建议先选取一个小型 Pattern 验证批处理流程，再处理全部生产文件。

## 11. 数据保密与问题反馈

生产 STIL 往往包含器件引脚、扫描链和测试向量等敏感信息。提交 GitHub Issue 时请勿上传：

- 完整量产 STIL
- 网表或扫描单元名称
- 真实产品 Pin Map
- 器件专用电压和限制

请构造最小化的合成 STIL，只保留能够复现问题的结构。提交问题时建议附上：

- 软件版本
- Windows 版本
- 是否勾选完全展开和 NI 编译
- 完整错误文本
- 已脱敏的最小输入
- `conversion_report.txt` 中不敏感的统计信息

问题反馈地址：[GitHub Issues](https://github.com/dong7727/stil-to-ni-digital/issues)

## 12. 重要安全说明

数字 Pattern、Timing、Pin Map 或电压配置错误可能导致误判，严重时可能损坏 DUT、负载板或测试仪器。转换结果必须经过工程审核、仿真或 golden device 验证，不能仅凭“转换成功”直接投入生产。

本项目独立开发，与 National Instruments 或 Synopsys 无隶属或背书关系。NI、NI-Digital、TetraMAX 及其他产品名称归各自权利人所有。
