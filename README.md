# 表单自动填写助手

基于 Chrome DevTools Protocol (CDP) 的浏览器自动化表单填写工具，**无需安装浏览器扩展**，直接控制您日常使用的 Edge/Chrome 浏览器，一键自动填写腾讯文档、问卷星、WPS表单、金数据、石墨表单等多种平台的表单。

## ✨ 功能特点

- **免扩展**：纯 Python + CDP 协议，不依赖 Tampermonkey、Playwright 或 Selenium。
- **日常浏览器**：直接使用您正在使用的 Edge/Chrome，保留书签、密码、登录状态。
- **多平台支持**：精准适配腾讯文档、麦客CRM、问卷星、WPS表单、金数据、石墨表单等。
- **多填写方案**：每条规则可预设多个填写值，双击单元格即可切换，满足不同场景。
- **轻量 GUI**：tkinter 界面，启动/停止一键控制，日志实时显示。
- **外部链接自动触发**：从微信/QQ 点击表单链接，新标签页打开后自动填写。
- **完全离线**：所有数据本地存储（JSON），无需网络。

## 📋 支持平台

| 平台 | 示例域名 |
|------|---------|
| 腾讯文档 | `docs.qq.com/form/*` |
| 麦客CRM | `*.mikecrm.com`, `*.mike-x.com` |
| 问卷星 | `www.wjx.cn/vm/*`, `v.wjx.cn/vm/*` 等 |
| WPS 表单 | `f.wps.cn/ksform/w/write/*`, `f.kdocs.cn/ksform/w/write/*` |
| 金数据 | `jsj.top/f/*` |
| 石墨表单 | `shimo.im/forms/*/fill` |

## 🚀 快速开始

### 1. 环境要求
- Windows 10/11（macOS 需自行调整浏览器路径）
- Python 3.9+
- Edge 或 Chrome 浏览器

### 2. 安装依赖
```bash
pip install websockets
```
注：tkinter 通常随 Python 安装，若缺失请参考 Python 官方文档补装。

### 3. 运行程序
```bash
python auto_fill_cdp.py
```
程序将提示关闭已有的浏览器窗口并重新打开（调试模式）。
启动后，从微信/QQ 点击任何表单链接，或直接在浏览器地址栏粘贴链接，页面会自动填写。
点击界面上的"编辑答案"按钮可增删改规则，双击"填写值"列可切换当前激活的答案。

### 4. 命令行模式（无 GUI）
```bash
python auto_fill_cdp.py --no-gui --browser edge
```

### 5. 自定义答案配置
默认答案已内置，如需自定义，可编辑同目录下的 `answers.json`，或通过 GUI "编辑答案" 保存。
