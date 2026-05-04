#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
auto_fill_cdp.py
自动表单填写工具 —— 基于 CDP (Chrome DevTools Protocol) 的浏览器自动化脚本。

核心特性：
1. 使用 CDP 协议通过 websockets 直连浏览器，彻底移除 Playwright/Selenium 依赖。
2. 保留 auto_fill.py 中经过完整验证的 build_inject_script() 生成的 JS 注入脚本，
   对腾讯文档、麦客、问卷星、WPS、金数据、石墨表单等平台具备精确的标题提取和控件匹配能力。
3. 保留 tkinter GUI（启动/停止按钮、日志窗口、配置文件选择）、窗口关闭拦截、配置文件外部加载等功能。
4. 直接控制用户日常使用的 Edge/Chrome 浏览器（保留书签、插件、登录状态），
   以远程调试模式重启后，外部链接自动跳转到该浏览器并自动填写表单。
5. 支持每条规则独立选择激活值，双击编辑窗口单元格即可下拉选择。

依赖：websockets（异步网络）
"""

import argparse
import asyncio
import json
import os
import subprocess
import sys
import threading
import time
import tkinter as tk
import urllib.request
from fnmatch import fnmatch
from tkinter import filedialog, messagebox, scrolledtext, ttk
from typing import Dict, Optional

# 尝试导入 websockets，若失败则提示安装
try:
    import websockets
except ImportError:
    websockets = None


# ========== 默认答案配置（支持多方案 values） ==========
DEFAULT_ANSWER_CONFIG = [
    {"keywords": ["昵称", "账号昵称", "小红书昵称", "主页名称", "小红书名", "达人名称", "小红书账号名", "账号名称", "红书昵称", "博主名称", "账号名字"], "values": ["时悦Berry"], "active_index": 0},
    {"keywords": ["id", "主页id", "小红书id", "ID", "账号ID", "账户ID", "小红书号", "红书号", "小红书帐号", "微信ID"], "values": ["437399948"], "active_index": 0},
    {"keywords": ["粉丝数", "粉丝", "粉丝数量", "粉丝量", "粉丝总数", "关注数", "红书粉丝数"], "values": ["55000"], "active_index": 0},
    {"keywords": ["分发", "是否免费", "免费"], "values": ["是"], "active_index": 0},
    {"keywords": ["分发", "同步"], "values": ["抖音、点评"], "active_index": 0},
    {"keywords": ["机构"], "values": ["无"], "active_index": 0},
    {"keywords": ["赞藏量", "获赞", "收藏量", "点赞收藏数", "点赞数", "赞藏数", "赞藏总数", "赞藏", "红书赞藏量"], "values": ["265000"], "active_index": 0},
    {"keywords": ["主页链接", "小红书链接", "个人主页链接", "账号链接", "链接", "小红书主页", "红书链接", "主页"], "values": ["https://www.xiaohongshu.com/user/profile/5cb5fc910000000012031b54?xsec_token=ABaBuTo-HYttuFZGpBoMIk1XrfTvKtvQv2eM7cU6n_cos%3D&xsec_source=pc_search"], "active_index": 0},
    {"keywords": ["非报备图文", "水下图文", "未报备图文", "无报备图文", "非报备图文费用", "非报备图文价格"], "values": ["500", "800"], "active_index": 0},
    {"keywords": ["非报备视频", "水下视频", "未报备视频", "无报备视频", "非报备视频费用", "非报备视频价格"], "values": ["900", "1200"], "active_index": 0},
    {"keywords": ["报备图文", "报备 图文", "报备原创图文价格", "有报备图文", "报备图文费用", "报备图文价格", "红书图文报备报价", "图文报备报价"], "values": ["3000", "3500"], "active_index": 0},
    {"keywords": ["报备视频", "报备 视频", "报备原创视频价格", "有报备视频", "报备视频费用", "报备视频价格", "报备类视频价格"], "values": ["5000", "5500"], "active_index": 0},
    {"keywords": ["返点", "返点比例", "返利", "佣金比例", "返佣", "提成", "图文报备返点比例"], "values": ["45"], "active_index": 0},
    {"keywords": ["手机号", "电话", "联系方式", "电话号码", "手机号码", "联系电话", "电话号", "联系VX"], "values": ["16638548059"], "active_index": 0},
    {"keywords": ["微信号", "微信", "微信账号", "微信联系方式", "wx号", "微信ID", "wx", "微信昵称"], "values": ["16638548059"], "active_index": 0},
    {"keywords": ["账号类型", "小红书类型", "账号类别", "账号属性", "账号定位", "达人类型", "类型", "领域"], "values": ["时尚颜值探店"], "active_index": 0},
    {"keywords": ["平台", "发布平台", "运营平台", "推广平台", "合作平台"], "values": ["小红书"], "active_index": 0},
    {"keywords": ["个人博主", "是否个人博主", "个人账号", "博主类型"], "values": ["个人"], "active_index": 0},
    {"keywords": ["联系人", "姓名", "你的姓名"], "values": ["小欣"], "active_index": 0},
    {"keywords": ["费用", "预算", "合作费用", "稿费"], "values": ["500", "600"], "active_index": 0},
    {"keywords": ["均赞", "平均点赞", "平均赞"], "values": ["1500"], "active_index": 0},
]

# ========== URL 匹配规则（决定哪些站点启用自动填写） ==========
URL_PATTERNS = [
    "*://docs.qq.com/form/*",
    "*://*.mikecrm.com/*",
    "*://*.mike-x.com/*",
    "*://www.wenjuan.com/s/*",
    "*://v.wjx.cn/vm/*",
    "*://www.wjx.top/vm/*",
    "*://www.wjx.cn/vm/*",
    "*://f.kdocs.cn/ksform/w/write/*",
    "*://f.wps.cn/ksform/w/write/*",
    "*://jsj.top/f/*",
    "*://shimo.im/forms/*/fill",
]


# ========== 浏览器路径与用户数据目录相关函数 ==========

def find_browser_path(channel: str) -> str | None:
    """
    在 Windows 默认安装路径查找浏览器可执行文件。
    Edge 优先查找 Program Files (x86) 和 Program Files 下的 msedge.exe。
    Chrome 优先查找 Program Files 和 Program Files (x86) 下的 chrome.exe。
    返回完整路径或 None。
    """
    if channel == "edge":
        candidates = [
            r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        ]
    else:
        candidates = [
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        ]
    for path in candidates:
        if os.path.exists(path):
            return path
    return None


def get_default_browser_info(channel: str) -> dict:
    """
    获取系统默认浏览器信息和用户数据目录。
    返回 {"path": str, "user_data_dir": str}，找不到则返回空字典。
    """
    browser_path = find_browser_path(channel)
    if not browser_path:
        return {}

    local_appdata = os.environ.get("LOCALAPPDATA", "")
    if not local_appdata:
        return {}

    if channel == "edge":
        user_data_dir = os.path.join(local_appdata, r"Microsoft\Edge\User Data")
    else:
        user_data_dir = os.path.join(local_appdata, r"Google\Chrome\User Data")

    if not os.path.exists(user_data_dir):
        return {}

    return {"path": browser_path, "user_data_dir": user_data_dir}


async def restart_browser_with_debug(browser_path: str, user_data_dir: str) -> subprocess.Popen | None:
    """
    以远程调试模式重启浏览器。
    1. 先检查 9222 端口是否已有调试实例在运行，若已可用则直接返回 None（无需重启）。
    2. 否则终止现有浏览器进程，等待后重新启动带 --remote-debugging-port=9222 的实例。
    3. 轮询等待 CDP 端口就绪，最多 20 秒。
    返回浏览器进程对象，或 None（端口已就绪）。
    """
    # 检查是否已有调试实例在运行
    try:
        with urllib.request.urlopen("http://127.0.0.1:9222/json/version", timeout=2):
            return None
    except Exception:
        pass

    # 终止现有浏览器进程
    exe_name = os.path.basename(browser_path)
    try:
        subprocess.run(["taskkill", "/F", "/IM", exe_name], capture_output=True, check=False)
        await asyncio.sleep(2)
    except Exception:
        pass

    # 启动带远程调试端口的浏览器
    cmd = [
        browser_path,
        f"--user-data-dir={user_data_dir}",
        "--profile-directory=Default",
        "--remote-debugging-port=9222",
        "--no-first-run",
        "--disable-popup-blocking",
        "--disable-infobars",
        "--window-size=1366,768",
        "--window-name=自动填写助手",
    ]
    process = subprocess.Popen(cmd)

    # 轮询等待 CDP 端口就绪
    for _ in range(40):
        try:
            with urllib.request.urlopen("http://127.0.0.1:9222/json/version", timeout=1):
                break
        except Exception:
            await asyncio.sleep(0.5)
    else:
        process.terminate()
        return None

    return process


# ========== 表单填写 JS 注入脚本构造 ==========

def build_inject_script(answer_config_json: str) -> str:
    """
    构造需要注入页面的 JavaScript 自执行函数字符串。
    """
    script = (
        "(() => {\n"
        "    'use strict';\n"
        "\n"
        "    // 从 Python 端传入的答案配置\n"
        "    const ANSWER_CONFIG = " + answer_config_json + ";\n"
        "\n"
        "    // ========== 工具函数 ==========\n"
        "    function cleanText(text) {\n"
        "        if (!text || typeof text !== 'string') return '';\n"
        "        return text.toLowerCase()\n"
        "                   .replace(/[\\s\\n\\r\\t:：()（）【】、，。？！]/g, '')\n"
        "                   .replace(/[^\\u4e00-\\u9fa5a-zA-Z0-9]/g, '');\n"
        "    }\n"
        "\n"
        "    // 获取控件标题（增强麦客、问卷星等平台处理）\n"
        "    function getControlTitle(control) {\n"
        "        let rawTitle = '';\n"
        "\n"
        "        // 0. 问卷星平台特殊处理\n"
        "        if (window.location.href.includes('wjx.top') || window.location.href.includes('wjx.cn')) {\n"
        "            let fieldContainer = control.closest('.field, .ui-control, .question, .div_question');\n"
        "            if (fieldContainer) {\n"
        "                let label = fieldContainer.querySelector('.field-label, .question-title, .title, label');\n"
        "                if (label) {\n"
        "                    rawTitle = label.innerText;\n"
        "                    rawTitle = rawTitle.replace(/\\*+$/, '').trim();\n"
        "                }\n"
        "            }\n"
        "            if (!rawTitle) {\n"
        "                let prev = control.previousElementSibling;\n"
        "                if (prev && (prev.tagName === 'LABEL' || prev.classList?.contains('field-label'))) {\n"
        "                    rawTitle = prev.innerText.replace(/\\*+$/, '').trim();\n"
        "                }\n"
        "            }\n"
        "            if (!rawTitle) {\n"
        "                let parent = control.parentElement;\n"
        "                while (parent && parent !== document.body) {\n"
        "                    let text = parent.innerText;\n"
        "                    if (text && text.length > 1) {\n"
        "                        let firstLine = text.split('\\n')[0];\n"
        "                        if (firstLine.length < 50) {\n"
        "                            rawTitle = firstLine.replace(/\\*+$/, '').trim();\n"
        "                            break;\n"
        "                        }\n"
        "                    }\n"
        "                    parent = parent.parentElement;\n"
        "                }\n"
        "            }\n"
        "        }\n"
        "\n"
        "        // 1. 麦客表单特殊处理\n"
        "        else if (window.location.hostname.includes('mikecrm') || window.location.hostname.includes('mike-x')) {\n"
        "            let field = control.closest('.field');\n"
        "            if (field) {\n"
        "                let label = field.querySelector('.field-label, label, .label');\n"
        "                if (label) {\n"
        "                    rawTitle = label.innerText;\n"
        "                    rawTitle = rawTitle.split(/[（(]/)[0].trim();\n"
        "                }\n"
        "            }\n"
        "            if (!rawTitle) {\n"
        "                let prev = control.previousElementSibling;\n"
        "                if (prev && (prev.classList?.contains('field-label') || prev.tagName === 'LABEL')) {\n"
        "                    rawTitle = prev.innerText;\n"
        "                    rawTitle = rawTitle.split(/[（(]/)[0].trim();\n"
        "                }\n"
        "            }\n"
        "            if (!rawTitle) {\n"
        "                let parent = control.closest('div');\n"
        "                while (parent && parent !== document.body) {\n"
        "                    let candidate = parent.querySelector('.field-label, label, .label');\n"
        "                    if (candidate) {\n"
        "                        rawTitle = candidate.innerText;\n"
        "                        rawTitle = rawTitle.split(/[（(]/)[0].trim();\n"
        "                        break;\n"
        "                    }\n"
        "                    parent = parent.parentElement;\n"
        "                }\n"
        "            }\n"
        "        }\n"
        "\n"
        "        // 2. 石墨文档平台特殊处理\n"
        "        else if (window.location.hostname === 'shimo.im') {\n"
        "            let fieldContainer = control.closest('.form-field');\n"
        "            if (fieldContainer) {\n"
        "                let label = fieldContainer.querySelector('.field-label, label');\n"
        "                if (label) rawTitle = label.innerText;\n"
        "            }\n"
        "            if (!rawTitle) {\n"
        "                let prev = control.previousElementSibling;\n"
        "                if (prev && (prev.classList.contains('label') || prev.tagName === 'LABEL')) {\n"
        "                    rawTitle = prev.innerText;\n"
        "                }\n"
        "            }\n"
        "        }\n"
        "\n"
        "        // 3. 金数据平台特殊处理\n"
        "        else if (window.location.hostname === 'jsj.top') {\n"
        "            let prev = control.previousElementSibling;\n"
        "            if (prev && prev.classList && prev.classList.contains('field-label')) {\n"
        "                rawTitle = prev.innerText;\n"
        "            }\n"
        "            if (!rawTitle) {\n"
        "                let wrapper = control.closest('.field-wrapper, .field');\n"
        "                if (wrapper) {\n"
        "                    let label = wrapper.querySelector('.field-label, .label, label');\n"
        "                    if (label) rawTitle = label.innerText;\n"
        "                }\n"
        "            }\n"
        "            if (!rawTitle) {\n"
        "                let parent = control.parentElement;\n"
        "                if (parent) {\n"
        "                    let possibleLabel = parent.querySelector('label, .field-label');\n"
        "                    if (possibleLabel) rawTitle = possibleLabel.innerText;\n"
        "                }\n"
        "            }\n"
        "        }\n"
        "\n"
        "        // 4. 通用逻辑：尝试获取关联的 label\n"
        "        if (!rawTitle && control.labels && control.labels.length > 0) {\n"
        "            rawTitle = control.labels[0].innerText;\n"
        "        }\n"
        "\n"
        "        // 5. 尝试获取父级容器的文本（向上查找10层）\n"
        "        if (!rawTitle) {\n"
        "            var parent = control;\n"
        "            var maxDepth = 10;\n"
        "            var depth = 0;\n"
        "            while (parent && depth < maxDepth) {\n"
        "                var text = parent.innerText || '';\n"
        "                if (text.length > 1) {\n"
        "                    rawTitle = text;\n"
        "                    break;\n"
        "                }\n"
        "                parent = parent.parentElement;\n"
        "                depth++;\n"
        "            }\n"
        "        }\n"
        "\n"
        "        // 6. 最后尝试 placeholder 属性\n"
        "        if (!rawTitle && control.placeholder) {\n"
        "            rawTitle = control.placeholder;\n"
        "        }\n"
        "\n"
        "        // 针对腾讯文档，去除开头的序号\n"
        "        if (window.location.hostname === 'docs.qq.com' && rawTitle) {\n"
        "            rawTitle = rawTitle.replace(/^[\\d\\*\\.\\s]+/g, '');\n"
        "        }\n"
        "\n"
        "        return cleanText(rawTitle || '');\n"
        "    }\n"
        "\n"
        "    function getAnswerByTitle(title) {\n"
        "        let matches = [];\n"
        "        for (let item of ANSWER_CONFIG) {\n"
        "            for (let keyword of item.keywords) {\n"
        "                let cleanKeyword = cleanText(keyword);\n"
        "                if (title.includes(cleanKeyword)) {\n"
        "                    matches.push({ keyword: keyword, answer: item.value, length: cleanKeyword.length });\n"
        "                }\n"
        "            }\n"
        "        }\n"
        "        if (matches.length === 0) return null;\n"
        "        matches.sort((a, b) => b.length - a.length);\n"
        "        console.log('🎯 匹配到关键词: \"' + matches[0].keyword + '\" -> 答案: \"' + matches[0].answer + '\"');\n"
        "        return matches[0].answer;\n"
        "    }\n"
        "\n"
        "    function fillControl(control, answer) {\n"
        "        if (control.getAttribute('data-filled') === 'true') return false;\n"
        "\n"
        "        try {\n"
        "            // 文本输入框 / 文本域\n"
        "            if ((control.tagName === 'INPUT' && ['text','number','email','tel','url'].includes(control.type)) || control.tagName === 'TEXTAREA') {\n"
        "                const nativeInputValueSetter = Object.getOwnPropertyDescriptor(\n"
        "                    Object.getPrototypeOf(control),\n"
        "                    'value'\n"
        "                )?.set;\n"
        "                if (nativeInputValueSetter) {\n"
        "                    nativeInputValueSetter.call(control, answer);\n"
        "                } else {\n"
        "                    control.value = answer;\n"
        "                }\n"
        "\n"
        "                control.dispatchEvent(new Event('input', { bubbles: true }));\n"
        "                control.dispatchEvent(new Event('change', { bubbles: true }));\n"
        "\n"
        "                setTimeout(() => {\n"
        "                    control.dispatchEvent(new Event('blur', { bubbles: true }));\n"
        "                }, 10);\n"
        "\n"
        "                control.setAttribute('data-filled', 'true');\n"
        "                console.log('✅ 填写文本框: ' + answer);\n"
        "                return true;\n"
        "            }\n"
        "\n"
        "            // 单选框\n"
        "            if (control.tagName === 'INPUT' && control.type === 'radio') {\n"
        "                let labelText = cleanText(control.closest('label') ? control.closest('label').innerText : '');\n"
        "                if (labelText.includes(cleanText(answer)) || cleanText(control.value).includes(cleanText(answer))) {\n"
        "                    control.checked = true;\n"
        "                    control.dispatchEvent(new Event('change', { bubbles: true }));\n"
        "                    setTimeout(() => {\n"
        "                        control.dispatchEvent(new Event('blur', { bubbles: true }));\n"
        "                    }, 10);\n"
        "                    control.setAttribute('data-filled', 'true');\n"
        "                    console.log('✅ 选中单选框: ' + control.value);\n"
        "                    return true;\n"
        "                }\n"
        "                return false;\n"
        "            }\n"
        "\n"
        "            // 复选框\n"
        "            if (control.tagName === 'INPUT' && control.type === 'checkbox') {\n"
        "                let cbLabelText = cleanText(control.closest('label') ? control.closest('label').innerText : '');\n"
        "                if (cbLabelText.includes(cleanText(answer)) || cleanText(control.value).includes(cleanText(answer))) {\n"
        "                    control.checked = true;\n"
        "                    control.dispatchEvent(new Event('change', { bubbles: true }));\n"
        "                    setTimeout(() => {\n"
        "                        control.dispatchEvent(new Event('blur', { bubbles: true }));\n"
        "                    }, 10);\n"
        "                    control.setAttribute('data-filled', 'true');\n"
        "                    console.log('✅ 勾选复选框: ' + control.value);\n"
        "                    return true;\n"
        "                }\n"
        "                return false;\n"
        "            }\n"
        "\n"
        "            // 下拉框\n"
        "            if (control.tagName === 'SELECT') {\n"
        "                let options = control.options;\n"
        "                for (let j = 0; j < options.length; j++) {\n"
        "                    let opt = options[j];\n"
        "                    if (cleanText(opt.text).includes(cleanText(answer)) || cleanText(opt.value).includes(cleanText(answer))) {\n"
        "                        control.value = opt.value;\n"
        "                        control.dispatchEvent(new Event('change', { bubbles: true }));\n"
        "                        setTimeout(() => {\n"
        "                            control.dispatchEvent(new Event('blur', { bubbles: true }));\n"
        "                    }, 10);\n"
        "                        control.setAttribute('data-filled', 'true');\n"
        "                        console.log('✅ 选择下拉框: ' + opt.text);\n"
        "                        return true;\n"
        "                    }\n"
        "                }\n"
        "                return false;\n"
        "            }\n"
        "        } catch (e) {\n"
        "            console.error('❌ 填写控件失败: ' + e.message);\n"
        "        }\n"
        "        return false;\n"
        "    }\n"
        "\n"
        "    function autoFillAll() {\n"
        "        console.log('🔍 开始自动填写...');\n"
        "        let successCount = 0;\n"
        "        let allControls = document.querySelectorAll('input:not([type=\"hidden\"]), textarea, select');\n"
        "        console.log('📋 共找到 ' + allControls.length + ' 个控件');\n"
        "\n"
        "        let processedControls = new Set();\n"
        "\n"
        "        for (let control of allControls) {\n"
        "            if (processedControls.has(control)) continue;\n"
        "            processedControls.add(control);\n"
        "\n"
        "            let title = getControlTitle(control);\n"
        "            console.log('🔎 控件: ' + control.tagName + '.' + control.type + ' -> 标题: \"' + title + '\"');\n"
        "\n"
        "            if (!title) {\n"
        "                console.log('   ⚠️ 无法提取标题');\n"
        "                continue;\n"
        "            }\n"
        "\n"
        "            let answer = getAnswerByTitle(title);\n"
        "            if (!answer) {\n"
        "                console.log('   ❌ 无匹配答案');\n"
        "                continue;\n"
        "            }\n"
        "            console.log('   ✅ 匹配答案: ' + answer);\n"
        "\n"
        "            if (control.type === 'radio' || control.type === 'checkbox') {\n"
        "                let name = control.name;\n"
        "                if (name) {\n"
        "                    let groupControls = document.querySelectorAll('input[name=\"' + name + '\"]');\n"
        "                    for (let gc of groupControls) {\n"
        "                        processedControls.add(gc);\n"
        "                    }\n"
        "                    let filled = false;\n"
        "                    for (let gc of groupControls) {\n"
        "                        if (fillControl(gc, answer)) {\n"
        "                            filled = true;\n"
        "                            successCount++;\n"
        "                            break;\n"
        "                        }\n"
        "                    }\n"
        "                    if (!filled) {\n"
        "                        console.log('   ⚠️ 未找到匹配选项: ' + title);\n"
        "                    }\n"
        "                } else {\n"
        "                    if (fillControl(control, answer)) successCount++;\n"
        "                }\n"
        "            } else {\n"
        "                if (fillControl(control, answer)) successCount++;\n"
        "            }\n"
        "        }\n"
        "\n"
        "        console.log('✅ 本次填写完成！成功填写 ' + successCount + ' 个字段');\n"
        "        return successCount;\n"
        "    }\n"
        "\n"
        "    function addManualButton() {\n"
        "        if (document.getElementById('__auto_fill_btn__')) return;\n"
        "        let btn = document.createElement('button');\n"
        "        btn.id = '__auto_fill_btn__';\n"
        "        btn.textContent = '📝 自动填写表单';\n"
        "        btn.style.cssText = 'position: fixed; bottom: 20px; right: 20px; z-index: 9999; background: #4CAF50; color: white; border: none; border-radius: 5px; padding: 8px 16px; cursor: pointer; font-size: 14px; box-shadow: 0 2px 5px rgba(0,0,0,0.2); font-family: sans-serif;';\n"
        "        btn.onclick = () => {\n"
        "            document.querySelectorAll('[data-filled=\"true\"]').forEach(el => el.removeAttribute('data-filled'));\n"
        "            autoFillAll();\n"
        "        };\n"
        "        document.body.appendChild(btn);\n"
        "    }\n"
        "\n"
        "    window.dumpFormFields = function() {\n"
        "        document.querySelectorAll('input:not([type=\"hidden\"]), textarea, select').forEach(ctrl => {\n"
        "            let title = getControlTitle(ctrl);\n"
        "            let answer = getAnswerByTitle(title);\n"
        "            console.group('控件: ' + ctrl.tagName + '.' + (ctrl.type || 'unknown'));\n"
        "            console.log('HTML:', ctrl);\n"
        "            console.log('标题:', title);\n"
        "            console.log('匹配答案:', answer);\n"
        "            console.groupEnd();\n"
        "        });\n"
        "    };\n"
        "\n"
        "    function init() {\n"
        "        autoFillAll();\n"
        "        addManualButton();\n"
        "\n"
        "        let observer = new MutationObserver(() => {\n"
        "            clearTimeout(window.fillDebounceTimer);\n"
        "            window.fillDebounceTimer = setTimeout(autoFillAll, 800);\n"
        "        });\n"
        "\n"
        "        observer.observe(document.body, {\n"
        "            childList: true,\n"
        "            subtree: true,\n"
        "            attributes: true,\n"
        "            attributeFilter: ['style', 'class']\n"
        "        });\n"
        "\n"
        "        setTimeout(() => observer.disconnect(), 30000);\n"
        "\n"
        "        let retryTimes = 0;\n"
        "        let retryInterval = setInterval(() => {\n"
        "            let success = autoFillAll();\n"
        "            retryTimes++;\n"
        "            if (success > 0 || retryTimes >= 5) {\n"
        "                clearInterval(retryInterval);\n"
        "            }\n"
        "        }, 1000);\n"
        "        setTimeout(() => clearInterval(retryInterval), 10000);\n"
        "    }\n"
        "\n"
        "    if (document.readyState === 'complete' || document.readyState === 'interactive') {\n"
        "        setTimeout(init, 100);\n"
        "    } else {\n"
        "        window.addEventListener('DOMContentLoaded', init);\n"
        "    }\n"
        "})();\n"
    )
    return script


# ========== CDP 客户端（精简版） ==========

class CDPClient:
    """
    Chrome DevTools Protocol 客户端（精简版）。
    仅保留连接、发送命令、注册事件处理器、关闭连接等核心功能。
    """

    def __init__(self, host: str = "127.0.0.1", port: int = 9222):
        self.host = host
        self.port = port
        self.ws = None
        self.ws_url = None
        self.message_id = 0
        self.event_handlers = {}
        self.response_futures = {}

    def _get_browser_info(self) -> Optional[Dict]:
        """通过 HTTP 获取浏览器信息和 WebSocket URL。"""
        try:
            url = f"http://{self.host}:{self.port}/json/version"
            with urllib.request.urlopen(url, timeout=5) as response:
                data = json.loads(response.read().decode("utf-8"))
                return data
        except Exception as e:
            print(f"获取浏览器信息失败: {e}")
            return None

    async def connect(self) -> bool:
        """连接到浏览器 CDP 端口。"""
        try:
            browser_info = self._get_browser_info()
            if not browser_info:
                print("无法获取浏览器信息")
                return False

            self.ws_url = browser_info.get("webSocketDebuggerUrl")
            if not self.ws_url:
                print("未找到 WebSocket URL")
                return False

            print(f"连接到: {self.ws_url}")

            self.ws = await websockets.connect(
                self.ws_url,
                ping_timeout=30,
                ping_interval=10,
            )

            asyncio.create_task(self._receive_messages())
            return True
        except Exception as e:
            print(f"CDP 连接失败: {e}")
            return False

    async def _receive_messages(self):
        """后台接收 CDP 消息，分发到事件处理器或响应 Future。"""
        try:
            async for message in self.ws:
                if isinstance(message, bytes):
                    continue

                data = json.loads(message)

                if "method" in data:
                    event_name = data["method"]
                    params = data.get("params", {})

                    if event_name in self.event_handlers:
                        for handler in self.event_handlers[event_name]:
                            try:
                                handler(params)
                            except Exception as e:
                                print(f"事件处理错误 {event_name}: {e}")

                elif "id" in data:
                    msg_id = data["id"]
                    if msg_id in self.response_futures:
                        future = self.response_futures.pop(msg_id)
                        if "error" in data:
                            future.set_result({"error": data["error"]})
                        else:
                            future.set_result(data.get("result", {}))
        except Exception as e:
            print(f"CDP 消息接收错误: {e}")

    def register_handler(self, event_name: str, handler):
        """注册事件处理器。"""
        if event_name not in self.event_handlers:
            self.event_handlers[event_name] = []
        self.event_handlers[event_name].append(handler)

    async def send_command(self, method: str, sessionId: str = None, **params) -> dict:
        """发送 CDP 命令并等待响应。"""
        if not self.ws:
            return {"error": "Not connected"}

        self.message_id += 1
        message = {
            "id": self.message_id,
            "method": method,
            "params": params,
        }

        if sessionId:
            message["sessionId"] = sessionId

        future = asyncio.Future()
        self.response_futures[self.message_id] = future

        await self.ws.send(json.dumps(message))

        try:
            return await asyncio.wait_for(future, timeout=30)
        except asyncio.TimeoutError:
            if self.message_id in self.response_futures:
                del self.response_futures[self.message_id]
            return {"error": "Timeout"}

    async def close(self):
        """关闭 WebSocket 连接。"""
        if self.ws:
            await self.ws.close()
            self.ws = None


class CDPBrowserManager:
    """CDP 浏览器管理器（精简版）。"""

    def __init__(self, cdp_client: CDPClient):
        self.cdp = cdp_client
        self.targets = {}

    async def list_targets(self) -> Dict:
        """列出所有 page 类型的标签页。"""
        result = await self.cdp.send_command("Target.getTargets")
        if "error" in result:
            print(f'获取标签页失败: {result["error"]}')
            return {}

        targets = result.get("targetInfos", [])
        self.targets = {
            t["targetId"]: t for t in targets if t.get("type") == "page"
        }
        return self.targets

    async def attach_to_target(self, target_id: str) -> Optional[str]:
        """附加到目标标签页，返回 sessionId。"""
        result = await self.cdp.send_command(
            "Target.attachToTarget",
            targetId=target_id,
            flatten=True,
        )
        if "error" in result:
            return None
        return result.get("sessionId")

    async def activate_target(self, target_id: str) -> bool:
        """激活目标标签页。"""
        result = await self.cdp.send_command("Target.activateTarget", targetId=target_id)
        return "error" not in result


# ========== 配置加载工具（支持每条规则独立选择激活值） ==========

def load_answer_config(config_path: str | None) -> dict:
    """
    加载答案配置，返回包含 answers 的字典。
    兼容旧格式（纯列表、含 value 字段、含 active_scheme 字段）。
    """
    raw_data = None
    if config_path and os.path.exists(config_path):
        with open(config_path, "r", encoding="utf-8") as f:
            raw_data = json.load(f)

    # 若文件不存在或读取失败，使用默认配置
    if raw_data is None:
        raw_data = DEFAULT_ANSWER_CONFIG

    # 处理旧格式：纯列表
    if isinstance(raw_data, list):
        answers = raw_data
    else:
        answers = raw_data.get("answers", raw_data.get("data", []))

    # 兼容旧格式：将 value 包装为 values 单元素列表
    for item in answers:
        if "value" in item and "values" not in item:
            item["values"] = [item.pop("value")]
        # 确保 values 是列表
        if "values" not in item:
            item["values"] = [""]
        # 确保有 active_index 字段，默认为 0
        if "active_index" not in item:
            item["active_index"] = 0

    return {"answers": answers}


def prepare_inject_config(config_dict: dict) -> list:
    """
    根据每条规则的 active_index 构造注入用的临时配置列表。
    输出格式为 {"keywords": [...], "value": "..."}。
    """
    answers = config_dict.get("answers", [])
    result = []
    for item in answers:
        values = item.get("values", [""])
        active_index = item.get("active_index", 0)
        # 若索引超出范围，取最后一个值
        val = values[min(active_index, len(values) - 1)] if values else ""
        result.append({"keywords": item.get("keywords", []), "value": val})
    return result


# ========== GUI 应用类 ==========

class AutoFillApp:
    """
    tkinter GUI 控制面板，用于启动和停止 CDP 自动填写服务。
    直接控制用户日常使用的浏览器，保留书签、插件、登录状态。
    """

    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("表单自动填写助手")
        self.root.geometry("520x420")
        self.root.resizable(False, False)

        # 运行状态
        self.is_running = False
        self.browser_thread = None
        self.stop_event = threading.Event()

        # CDP 相关对象
        self.cdp_client = None
        self.cdp_manager = None
        self.browser_process = None

        # 配置变量
        self.browser_var = tk.StringVar(value="edge")
        self.config_var = tk.StringVar(value="")

        # 浏览器路径
        self.browser_path = None

        # 当前内存中的答案配置（用于编辑窗口读取）
        self.answer_config = None

        self._build_ui()

        # 拦截窗口关闭事件，服务运行期间禁止关闭
        self.root.protocol("WM_DELETE_WINDOW", self._on_closing)

    def _build_ui(self):
        # 标题
        title = tk.Label(self.root, text="🚀 表单自动填写助手", font=("Microsoft YaHei", 16, "bold"))
        title.pack(pady=10)

        # 配置区域
        frame = tk.Frame(self.root)
        frame.pack(padx=20, pady=5, fill=tk.X)

        tk.Label(frame, text="浏览器:", font=("Microsoft YaHei", 10)).grid(row=0, column=0, sticky=tk.W, pady=5)
        browser_combo = ttk.Combobox(frame, textvariable=self.browser_var, values=["edge", "chrome"], state="readonly", width=10)
        browser_combo.grid(row=0, column=1, sticky=tk.W, padx=5)

        tk.Label(frame, text="配置文件:", font=("Microsoft YaHei", 10)).grid(row=1, column=0, sticky=tk.W, pady=5)
        tk.Entry(frame, textvariable=self.config_var, width=30).grid(row=1, column=1, sticky=tk.W, padx=5)
        tk.Button(frame, text="浏览...", command=self._browse_config).grid(row=1, column=2, padx=5)

        # 按钮区域
        btn_frame = tk.Frame(self.root)
        btn_frame.pack(pady=15)

        self.start_btn = tk.Button(btn_frame, text="▶ 启动服务", font=("Microsoft YaHei", 11), width=12,
                                   bg="#4CAF50", fg="white", command=self._start_service)
        self.start_btn.pack(side=tk.LEFT, padx=10)

        self.stop_btn = tk.Button(btn_frame, text="⏹ 停止服务", font=("Microsoft YaHei", 11), width=12,
                                  bg="#f44336", fg="white", command=self._stop_service, state=tk.DISABLED)
        self.stop_btn.pack(side=tk.LEFT, padx=10)

        # 编辑答案按钮
        self.edit_btn = tk.Button(btn_frame, text="✏ 编辑答案", font=("Microsoft YaHei", 11), width=12,
                                  bg="#2196F3", fg="white", command=self._open_editor)
        self.edit_btn.pack(side=tk.LEFT, padx=10)

        # 日志区域
        tk.Label(self.root, text="运行日志:", font=("Microsoft YaHei", 10)).pack(anchor=tk.W, padx=20)
        self.log_box = scrolledtext.ScrolledText(self.root, width=60, height=12, state=tk.DISABLED, font=("Consolas", 9))
        self.log_box.pack(padx=20, pady=5, fill=tk.BOTH, expand=True)

        # 状态栏
        self.status_label = tk.Label(self.root, text="状态: 已停止", font=("Microsoft YaHei", 9), fg="gray")
        self.status_label.pack(pady=5)

    def _browse_config(self):
        path = filedialog.askopenfilename(filetypes=[("JSON files", "*.json"), ("All files", "*.*")])
        if path:
            self.config_var.set(path)

    def _log(self, message: str):
        """向日志框追加带时间戳的消息。"""
        self.log_box.configure(state=tk.NORMAL)
        self.log_box.insert(tk.END, f"[{time.strftime('%H:%M:%S')}] {message}\n")
        self.log_box.see(tk.END)
        self.log_box.configure(state=tk.DISABLED)

    def _on_closing(self):
        """窗口关闭拦截：若服务正在运行，弹出警告阻止关闭；否则正常退出。"""
        if self.is_running:
            messagebox.showwarning("警告", "请先停止服务再关闭窗口！")
        else:
            self.root.destroy()

    def _open_editor(self):
        """
        打开"编辑答案库"窗口，允许用户增删改答案配置，支持每条规则独立选择激活值。
        双击"填写值"单元格可下拉选择具体值。
        数据来源于当前内存中的 answer_config，编辑后保存到 JSON 文件。
        """
        # 加载当前配置（若内存中无则读取文件或默认配置）
        if self.answer_config is None:
            self.answer_config = load_answer_config(self.config_var.get() or None)

        # 创建编辑窗口
        editor = tk.Toplevel(self.root)
        editor.title("编辑答案库")
        editor.geometry("680x450")
        editor.resizable(False, False)
        editor.transient(self.root)

        # Treeview 表格区域（带滚动条）
        tree_frame = tk.Frame(editor)
        tree_frame.pack(padx=10, pady=10, fill=tk.BOTH, expand=True)

        columns = ("keywords", "values")
        tree = ttk.Treeview(tree_frame, columns=columns, show="headings", height=14)
        tree.heading("keywords", text="匹配关键词（逗号分隔）")
        tree.heading("values", text="填写值（双击选择）")
        tree.column("keywords", width=360)
        tree.column("values", width=260)

        scrollbar = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)
        tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # 填充数据（使用编辑副本）
        edit_data = []
        for item in self.answer_config.get("answers", []):
            keywords = item.get("keywords", [])
            values = item.get("values", [""])
            active_index = item.get("active_index", 0)
            # 确保 active_index 在有效范围内
            if active_index >= len(values):
                active_index = 0
            display_value = values[active_index] if values else ""
            edit_data.append({"keywords": keywords, "values": values, "active_index": active_index})
            tree.insert("", tk.END, values=(", ".join(keywords), display_value))

        # 当前正在编辑的 Combobox 引用
        current_combo = {"widget": None, "item": None, "column": None}

        def _destroy_combo():
            """销毁当前打开的 Combobox。"""
            if current_combo["widget"] is not None:
                try:
                    current_combo["widget"].destroy()
                except Exception:
                    pass
                current_combo["widget"] = None
                current_combo["item"] = None
                current_combo["column"] = None

        def _on_tree_double_click(event):
            """双击 Treeview 单元格时，在 values 列弹出 Combobox 供选择。"""
            _destroy_combo()

            # 获取点击的行和列
            region = tree.identify_region(event.x, event.y)
            if region != "cell":
                return

            column = tree.identify_column(event.x)
            if column != "#2":  # 只处理 values 列
                return

            item = tree.identify_row(event.y)
            if not item:
                return

            idx = tree.index(item)
            if idx < 0 or idx >= len(edit_data):
                return

            data = edit_data[idx]
            values = data.get("values", [])
            if len(values) <= 1:
                # 只有一个值，无需选择
                return

            # 获取单元格坐标
            bbox = tree.bbox(item, column)
            if not bbox:
                return

            x, y, width, height = bbox

            # 创建 Combobox
            combo = ttk.Combobox(tree, values=values, state="readonly", width=30)
            combo.place(x=x, y=y, width=width, height=height)
            combo.set(values[data.get("active_index", 0)])

            current_combo["widget"] = combo
            current_combo["item"] = item
            current_combo["column"] = column

            def _on_combo_selected(event):
                """选择值后更新数据和 Treeview 显示。"""
                selected_value = combo.get()
                if selected_value in values:
                    new_index = values.index(selected_value)
                    edit_data[idx]["active_index"] = new_index
                    tree.item(item, values=(", ".join(data["keywords"]), selected_value))
                _destroy_combo()

            combo.bind("<<ComboboxSelected>>", _on_combo_selected)
            combo.bind("<FocusOut>", lambda e: _destroy_combo())
            combo.focus_set()

        def _on_tree_single_click(event):
            """单击其他位置时销毁 Combobox。"""
            if current_combo["widget"] is not None:
                region = tree.identify_region(event.x, event.y)
                if region != "cell":
                    _destroy_combo()
                    return
                column = tree.identify_column(event.x)
                item = tree.identify_row(event.y)
                if column != current_combo["column"] or item != current_combo["item"]:
                    _destroy_combo()

        tree.bind("<Double-Button-1>", _on_tree_double_click)
        tree.bind("<Button-1>", _on_tree_single_click)

        # 按钮区域
        btn_frame = tk.Frame(editor)
        btn_frame.pack(pady=10)

        def _add_rule():
            """弹出对话框添加新规则，支持多方案值（分号分隔）。"""
            add_win = tk.Toplevel(editor)
            add_win.title("添加规则")
            add_win.geometry("450x160")
            add_win.resizable(False, False)
            add_win.transient(editor)
            add_win.grab_set()

            tk.Label(add_win, text="关键词（逗号分隔）:", font=("Microsoft YaHei", 9)).grid(row=0, column=0, padx=5, pady=5, sticky=tk.W)
            kw_entry = tk.Entry(add_win, width=38)
            kw_entry.grid(row=0, column=1, padx=5, pady=5)

            tk.Label(add_win, text="填写值（分号分隔多方案）:", font=("Microsoft YaHei", 9)).grid(row=1, column=0, padx=5, pady=5, sticky=tk.W)
            val_entry = tk.Entry(add_win, width=38)
            val_entry.grid(row=1, column=1, padx=5, pady=5)
            tk.Label(add_win, text="例如: 500; 800", font=("Microsoft YaHei", 8), fg="gray").grid(row=2, column=1, sticky=tk.W, padx=5)

            def _confirm_add():
                kw_raw = kw_entry.get().strip()
                val_raw = val_entry.get().strip()
                if not kw_raw or not val_raw:
                    messagebox.showwarning("警告", "关键词和填写值不能为空！", parent=add_win)
                    return
                keywords = [k.strip() for k in kw_raw.split(",") if k.strip()]
                if not keywords:
                    messagebox.showwarning("警告", "至少输入一个有效关键词！", parent=add_win)
                    return
                values = [v.strip() for v in val_raw.split(";") if v.strip()]
                if not values:
                    values = [val_raw]
                edit_data.append({"keywords": keywords, "values": values, "active_index": 0})
                tree.insert("", tk.END, values=(", ".join(keywords), values[0]))
                add_win.destroy()

            tk.Button(add_win, text="确定", font=("Microsoft YaHei", 9), command=_confirm_add).grid(row=3, column=0, columnspan=2, pady=10)

        def _edit_rule():
            """弹出对话框修改选中规则。"""
            selected = tree.selection()
            if not selected:
                messagebox.showwarning("警告", "请先选中要修改的规则！", parent=editor)
                return
            item = selected[0]
            idx = tree.index(item)
            if idx < 0 or idx >= len(edit_data):
                return
            data = edit_data[idx]

            edit_win = tk.Toplevel(editor)
            edit_win.title("修改规则")
            edit_win.geometry("450x160")
            edit_win.resizable(False, False)
            edit_win.transient(editor)
            edit_win.grab_set()

            tk.Label(edit_win, text="关键词（逗号分隔）:", font=("Microsoft YaHei", 9)).grid(row=0, column=0, padx=5, pady=5, sticky=tk.W)
            kw_entry = tk.Entry(edit_win, width=38)
            kw_entry.insert(0, ", ".join(data["keywords"]))
            kw_entry.grid(row=0, column=1, padx=5, pady=5)

            tk.Label(edit_win, text="填写值（分号分隔多方案）:", font=("Microsoft YaHei", 9)).grid(row=1, column=0, padx=5, pady=5, sticky=tk.W)
            val_entry = tk.Entry(edit_win, width=38)
            val_entry.insert(0, "; ".join(data["values"]))
            val_entry.grid(row=1, column=1, padx=5, pady=5)
            tk.Label(edit_win, text="例如: 500; 800", font=("Microsoft YaHei", 8), fg="gray").grid(row=2, column=1, sticky=tk.W, padx=5)

            def _confirm_edit():
                kw_raw = kw_entry.get().strip()
                val_raw = val_entry.get().strip()
                if not kw_raw or not val_raw:
                    messagebox.showwarning("警告", "关键词和填写值不能为空！", parent=edit_win)
                    return
                keywords = [k.strip() for k in kw_raw.split(",") if k.strip()]
                if not keywords:
                    messagebox.showwarning("警告", "至少输入一个有效关键词！", parent=edit_win)
                    return
                values = [v.strip() for v in val_raw.split(";") if v.strip()]
                if not values:
                    values = [val_raw]
                # 保留原来的 active_index，如果新 values 长度变化则重置为 0
                active_index = data.get("active_index", 0)
                if active_index >= len(values):
                    active_index = 0
                edit_data[idx] = {"keywords": keywords, "values": values, "active_index": active_index}
                display_value = values[active_index] if values else ""
                tree.item(item, values=(", ".join(keywords), display_value))
                edit_win.destroy()

            tk.Button(edit_win, text="确定", font=("Microsoft YaHei", 9), command=_confirm_edit).grid(row=3, column=0, columnspan=2, pady=10)

        def _delete_rule():
            """删除 Treeview 中选中的规则。"""
            selected = tree.selection()
            if not selected:
                messagebox.showwarning("警告", "请先选中要删除的规则！", parent=editor)
                return
            for item in selected:
                idx = tree.index(item)
                tree.delete(item)
                if 0 <= idx < len(edit_data):
                    edit_data.pop(idx)

        def _save_and_close():
            """将编辑后的数据保存到 JSON 文件，并更新内存配置。"""
            save_path = self.config_var.get().strip()
            if not save_path:
                save_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "answers.json")

            save_dict = {
                "answers": edit_data,
            }

            try:
                with open(save_path, "w", encoding="utf-8") as f:
                    json.dump(save_dict, f, ensure_ascii=False, indent=2)
                self.config_var.set(save_path)
                self._log(f"答案配置已保存到: {save_path}")
            except Exception as e:
                messagebox.showerror("错误", f"保存失败: {e}", parent=editor)
                return

            # 重新加载配置到内存
            self.answer_config = load_answer_config(save_path)
            self._log("配置已更新，重启服务后生效。")
            editor.destroy()

        tk.Button(btn_frame, text="➕ 添加规则", font=("Microsoft YaHei", 10), command=_add_rule).pack(side=tk.LEFT, padx=5)
        tk.Button(btn_frame, text="✎ 修改选中", font=("Microsoft YaHei", 10), command=_edit_rule).pack(side=tk.LEFT, padx=5)
        tk.Button(btn_frame, text="➖ 删除选中", font=("Microsoft YaHei", 10), command=_delete_rule).pack(side=tk.LEFT, padx=5)
        tk.Button(btn_frame, text="💾 保存并关闭", font=("Microsoft YaHei", 10), command=_save_and_close).pack(side=tk.LEFT, padx=5)

    def _start_service(self):
        """启动服务：提示用户关闭浏览器、获取默认浏览器信息、重启为调试模式、连接 CDP。"""
        if self.is_running:
            return

        # 检查 websockets 依赖
        if websockets is None:
            messagebox.showerror("错误", "缺少 websockets 库！\n请运行: pip install websockets")
            return

        # 查找浏览器路径和默认用户数据目录
        browser_choice = self.browser_var.get()
        browser_info = get_default_browser_info(browser_choice)
        if not browser_info:
            messagebox.showerror("错误", f"未找到 {browser_choice.capitalize()} 浏览器或其用户数据目录！\n请确认已安装。")
            return

        self.browser_path = browser_info["path"]
        user_data_dir = browser_info["user_data_dir"]

        # 提示用户即将关闭浏览器窗口
        confirm = messagebox.askokcancel(
            "确认",
            f"程序将自动关闭您当前所有的 {browser_choice.capitalize()} 窗口，\n"
            "并重新启动以启用自动填写。\n\n"
            "请确保已保存工作内容。",
        )
        if not confirm:
            return

        self.is_running = True
        self.stop_event.clear()

        self.start_btn.configure(state=tk.DISABLED)
        self.stop_btn.configure(state=tk.NORMAL)
        self.status_label.configure(text="状态: 运行中", fg="green")

        self._log("正在启动浏览器服务...")
        self._log(f"使用默认用户数据目录: {user_data_dir}")

        # 在后台线程启动异步 CDP 浏览器管理
        self.browser_thread = threading.Thread(
            target=self._browser_worker,
            daemon=True,
            args=(user_data_dir,),
        )
        self.browser_thread.start()

    def _stop_service(self):
        """停止服务：关闭浏览器、断开 CDP。"""
        if not self.is_running:
            return
        self._log("正在停止服务...")
        self.stop_event.set()
        self.is_running = False

        self.start_btn.configure(state=tk.NORMAL)
        self.stop_btn.configure(state=tk.DISABLED)
        self.status_label.configure(text="状态: 已停止", fg="gray")

        # 通过 CDP 发送 Browser.close 关闭浏览器
        if self.cdp_client:
            try:
                asyncio.run_coroutine_threadsafe(
                    self.cdp_client.send_command("Browser.close"),
                    self._loop,
                )
            except Exception:
                pass

        # 终止浏览器进程
        if self.browser_process:
            try:
                self.browser_process.terminate()
                self.browser_process.wait(timeout=3)
            except Exception:
                pass
            self.browser_process = None

        # 断开 WebSocket
        if self.cdp_client:
            try:
                asyncio.run_coroutine_threadsafe(self.cdp_client.close(), self._loop)
            except Exception:
                pass
            self.cdp_client = None

        self._log("服务已停止。")

    def _browser_worker(self, user_data_dir: str):
        """
        在独立线程中运行 asyncio 事件循环，管理浏览器进程和 CDP 连接。
        """
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._async_browser_main(user_data_dir))
        except Exception as e:
            self._log(f"浏览器线程错误: {e}")
        finally:
            self._loop.close()
            self.is_running = False
            self.root.after(0, self._on_worker_finished)

    async def _async_browser_main(self, user_data_dir: str):
        """
        异步主逻辑：重启浏览器为调试模式、等待 CDP 就绪、连接、注入脚本、监听新页面。
        """
        browser_choice = self.browser_var.get()
        config_path = self.config_var.get() or None

        # 加载配置（含每条规则的 active_index）
        config_dict = load_answer_config(config_path)
        self.answer_config = config_dict

        if config_path:
            self._log(f"已加载外部配置: {config_path}")
        else:
            self._log("使用内置默认配置")

        # 构造注入用的临时配置（按每条规则的 active_index 取值）
        inject_config = prepare_inject_config(config_dict)
        answer_config_json = json.dumps(inject_config, ensure_ascii=False, indent=2)
        init_script = build_inject_script(answer_config_json)

        # 重启浏览器为远程调试模式（使用默认用户数据目录）
        self.browser_process = await restart_browser_with_debug(self.browser_path, user_data_dir)
        if self.browser_process is None:
            self._log("检测到已有调试实例，直接连接。")
        else:
            self._log(f"已重启 {browser_choice.capitalize()} 为调试模式。")

        # 等待 CDP 端口就绪
        for _ in range(10):
            if self.stop_event.is_set():
                return
            try:
                with urllib.request.urlopen("http://127.0.0.1:9222/json/version", timeout=1):
                    break
            except Exception:
                await asyncio.sleep(0.5)
        else:
            self._log("浏览器 CDP 端口未就绪，启动失败。")
            return

        # 连接 CDP
        self.cdp_client = CDPClient(host="127.0.0.1", port=9222)
        if not await self.cdp_client.connect():
            self._log("CDP 连接失败。")
            return

        self.cdp_manager = CDPBrowserManager(self.cdp_client)

        # 对已有标签页使用 Page.addScriptToEvaluateOnNewDocument 预注入脚本
        targets = await self.cdp_manager.list_targets()
        for target_id in targets:
            session_id = await self.cdp_manager.attach_to_target(target_id)
            if session_id:
                await self.cdp_client.send_command("Page.enable", sessionId=session_id)
                await self.cdp_client.send_command(
                    "Page.addScriptToEvaluateOnNewDocument",
                    sessionId=session_id,
                    source=init_script,
                )
                # 立即手动执行一次，作为兜底
                await self.cdp_client.send_command(
                    "Runtime.evaluate",
                    sessionId=session_id,
                    expression=init_script,
                )

        # 注册 Target.targetCreated 事件，新标签页创建时同样预注入脚本
        async def on_target_created(params):
            target_info = params.get("targetInfo", {})
            if target_info.get("type") == "page":
                target_id = target_info.get("targetId")
                self._log(f"新页面打开: {target_info.get('url', '')}")
                await asyncio.sleep(0.5)
                session_id = await self.cdp_manager.attach_to_target(target_id)
                if session_id:
                    await self.cdp_client.send_command("Page.enable", sessionId=session_id)
                    await self.cdp_client.send_command(
                        "Page.addScriptToEvaluateOnNewDocument",
                        sessionId=session_id,
                        source=init_script,
                    )
                    # 立即手动执行一次，作为兜底
                    await self.cdp_client.send_command(
                        "Runtime.evaluate",
                        sessionId=session_id,
                        expression=init_script,
                    )

        self.cdp_client.register_handler("Target.targetCreated", lambda p: asyncio.create_task(on_target_created(p)))

        # 启用 Target 域以接收 targetCreated 事件
        await self.cdp_client.send_command("Target.setDiscoverTargets", discover=True)

        self._log("CDP 连接成功，自动填写服务已就绪。")

        # 保持运行直到收到停止信号
        while not self.stop_event.is_set():
            await asyncio.sleep(0.5)

    def _on_worker_finished(self):
        """后台线程结束后的 UI 状态更新。"""
        self.start_btn.configure(state=tk.NORMAL)
        self.stop_btn.configure(state=tk.DISABLED)
        self.status_label.configure(text="状态: 已停止", fg="gray")
        self._log("服务线程已结束。")


# ========== 命令行模式（无 GUI） ==========

async def run_cli(browser_choice: str, config_path: str | None):
    """命令行模式：重启浏览器为调试模式、连接 CDP、注入脚本、保持运行直到 Ctrl+C。"""
    browser_info = get_default_browser_info(browser_choice)
    if not browser_info:
        print(f"未找到 {browser_choice.capitalize()} 浏览器或其用户数据目录！")
        return

    browser_path = browser_info["path"]
    user_data_dir = browser_info["user_data_dir"]

    # 加载配置（含每条规则的 active_index）
    config_dict = load_answer_config(config_path)

    # 构造注入用的临时配置
    inject_config = prepare_inject_config(config_dict)
    answer_config_json = json.dumps(inject_config, ensure_ascii=False, indent=2)
    init_script = build_inject_script(answer_config_json)

    # 重启浏览器为调试模式
    process = await restart_browser_with_debug(browser_path, user_data_dir)
    if process is None:
        print("检测到已有调试实例，直接连接。")
    else:
        print(f"🚀 已重启 {browser_choice.capitalize()} 为调试模式。")

    try:
        for _ in range(10):
            try:
                with urllib.request.urlopen("http://127.0.0.1:9222/json/version", timeout=1):
                    break
            except Exception:
                await asyncio.sleep(0.5)
        else:
            print("浏览器 CDP 端口未就绪。")
            return

        cdp = CDPClient()
        if not await cdp.connect():
            print("CDP 连接失败。")
            return

        manager = CDPBrowserManager(cdp)
        targets = await manager.list_targets()
        for target_id in targets:
            session_id = await manager.attach_to_target(target_id)
            if session_id:
                await cdp.send_command("Page.enable", sessionId=session_id)
                await cdp.send_command(
                    "Page.addScriptToEvaluateOnNewDocument",
                    sessionId=session_id,
                    source=init_script,
                )
                # 立即手动执行一次，作为兜底
                await cdp.send_command(
                    "Runtime.evaluate",
                    sessionId=session_id,
                    expression=init_script,
                )

        async def on_target_created(params):
            target_info = params.get("targetInfo", {})
            if target_info.get("type") == "page":
                target_id = target_info.get("targetId")
                await asyncio.sleep(0.5)
                session_id = await manager.attach_to_target(target_id)
                if session_id:
                    await cdp.send_command("Page.enable", sessionId=session_id)
                    await cdp.send_command(
                        "Page.addScriptToEvaluateOnNewDocument",
                        sessionId=session_id,
                        source=init_script,
                    )
                    # 立即手动执行一次，作为兜底
                    await cdp.send_command(
                        "Runtime.evaluate",
                        sessionId=session_id,
                        expression=init_script,
                    )

        cdp.register_handler("Target.targetCreated", lambda p: asyncio.create_task(on_target_created(p)))
        await cdp.send_command("Target.setDiscoverTargets", discover=True)

        print("✅ 自动填写服务已就绪。按 Ctrl+C 停止。")

        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        print("\n👋 正在停止...")
    finally:
        try:
            await cdp.send_command("Browser.close")
            await cdp.close()
        except Exception:
            pass
        try:
            if process:
                process.terminate()
                process.wait(timeout=3)
        except Exception:
            pass
        print("🛑 浏览器已关闭，程序退出。")


# ========== 主入口 ==========

def main():
    parser = argparse.ArgumentParser(description="自动表单填写工具 —— 基于 CDP 协议")
    parser.add_argument("--browser", choices=["chrome", "edge"], default="edge", help="选择浏览器，默认 edge")
    parser.add_argument("--config", default=None, help="指定外部答案配置文件路径（JSON 格式）")
    parser.add_argument("--no-gui", action="store_true", help="不使用 GUI，直接以命令行模式启动")
    args = parser.parse_args()

    if args.no_gui:
        # 命令行模式
        asyncio.run(run_cli(args.browser, args.config))
    else:
        # GUI 模式
        root = tk.Tk()
        app = AutoFillApp(root)
        root.mainloop()


if __name__ == "__main__":
    main()
