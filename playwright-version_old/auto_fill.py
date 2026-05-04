#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
auto_fill.py
自动表单填写工具 —— 基于 Playwright 的浏览器自动化脚本。
功能：启动带本地用户数据的 Edge/Chrome 浏览器，在匹配的网站上自动填写表单。
行为与 Tampermonkey 脚本「时悦4.7-5.1.user.js」完全一致。

新增：
1. 使用 tkinter 提供 GUI 控制面板，可一键启动/停止浏览器服务。
2. 临时接管系统默认浏览器注册表，使微信/QQ 等外部链接自动跳转到受控浏览器窗口。
3. 服务停止或程序退出时自动恢复注册表，不留痕迹。
4. GUI 窗口在服务运行期间阻止关闭，防止误操作。
"""

import argparse
import atexit
import json
import os
import shutil
import sys
import threading
import time
import tkinter as tk
import winreg
from fnmatch import fnmatch
from tkinter import filedialog, messagebox, scrolledtext, ttk

from playwright.sync_api import sync_playwright


# ========== 默认答案配置（与原始 Tampermonkey 脚本一致） ==========
DEFAULT_ANSWER_CONFIG = [
    {"keywords": ["昵称", "账号昵称", "小红书昵称", "主页名称", "小红书名", "达人名称", "小红书账号名", "账号名称", "红书昵称", "博主名称", "账号名字"], "value": "时悦Berry"},
    {"keywords": ["id", "主页id", "小红书id", "ID", "账号ID", "账户ID", "小红书号", "红书号", "小红书帐号", "微信ID"], "value": "437399948"},
    {"keywords": ["粉丝数", "粉丝", "粉丝数量", "粉丝量", "粉丝总数", "关注数", "红书粉丝数"], "value": "55000"},
    {"keywords": ["分发", "是否免费", "免费"], "value": "是"},
    {"keywords": ["分发", "同步"], "value": "抖音、点评"},
    {"keywords": ["机构"], "value": "无"},
    {"keywords": ["赞藏量", "获赞", "收藏量", "点赞收藏数", "点赞数", "赞藏数", "赞藏总数", "赞藏", "红书赞藏量"], "value": "265000"},
    {"keywords": ["主页链接", "小红书链接", "个人主页链接", "账号链接", "链接", "小红书主页", "红书链接", "主页"], "value": "https://www.xiaohongshu.com/user/profile/5cb5fc910000000012031b54?xsec_token=ABaBuTo-HYttuFZGpBoMIk1XrfTvKtvQv2eM7cU6n_cos%3D&xsec_source=pc_search"},
    {"keywords": ["非报备图文", "水下图文", "未报备图文", "无报备图文", "非报备图文费用", "非报备图文价格"], "value": "500"},
    {"keywords": ["非报备视频", "水下视频", "未报备视频", "无报备视频", "非报备视频费用", "非报备视频价格"], "value": "900"},
    {"keywords": ["报备图文", "报备 图文", "报备原创图文价格", "有报备图文", "报备图文费用", "报备图文价格", "红书图文报备报价", "图文报备报价"], "value": "3000"},
    {"keywords": ["报备视频", "报备 视频", "报备原创视频价格", "有报备视频", "报备视频费用", "报备视频价格", "报备类视频价格"], "value": "5000"},
    {"keywords": ["返点", "返点比例", "返利", "佣金比例", "返佣", "提成", "图文报备返点比例"], "value": "45"},
    {"keywords": ["手机号", "电话", "联系方式", "电话号码", "手机号码", "联系电话", "电话号", "联系VX"], "value": "16638548059"},
    {"keywords": ["微信号", "微信", "微信账号", "微信联系方式", "wx号", "微信ID", "wx", "微信昵称"], "value": "16638548059"},
    {"keywords": ["账号类型", "小红书类型", "账号类别", "账号属性", "账号定位", "达人类型", "类型", "领域"], "value": "时尚颜值探店"},
    {"keywords": ["平台", "发布平台", "运营平台", "推广平台", "合作平台"], "value": "小红书"},
    {"keywords": ["个人博主", "是否个人博主", "个人账号", "博主类型"], "value": "个人"},
    {"keywords": ["联系人", "姓名", "你的姓名"], "value": "小欣"},
    {"keywords": ["费用", "预算", "合作费用", "稿费"], "value": "500"},
    {"keywords": ["均赞", "平均点赞", "平均赞"], "value": "1500"},
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


# ========== 注册表与浏览器路径相关函数 ==========

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


def backup_registry() -> dict:
    r"""
    备份 HKEY_CURRENT_USER\Software\Classes\http\shell\open\command
    和 https\shell\open\command 的默认值。
    返回 {"http": 原值, "https": 原值} 的字典。
    """
    backup = {}
    for protocol in ("http", "https"):
        try:
            key_path = f"Software\\Classes\\{protocol}\\shell\\open\\command"
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path) as key:
                value, _ = winreg.QueryValueEx(key, None)
                backup[protocol] = value
        except Exception:
            backup[protocol] = None
    return backup


def restore_registry(backup: dict) -> None:
    """
    使用 backup_registry 返回的备份字典恢复注册表默认值。
    若备份值为 None 则跳过该协议。
    """
    if not backup:
        return
    for protocol in ("http", "https"):
        original = backup.get(protocol)
        if original is None:
            continue
        try:
            key_path = f"Software\\Classes\\{protocol}\\shell\\open\\command"
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE) as key:
                winreg.SetValueEx(key, None, 0, winreg.REG_SZ, original)
        except Exception as e:
            print(f"[WARN] 恢复 {protocol} 注册表失败: {e}")


def set_as_default(browser_path: str, user_data_dir: str) -> None:
    """
    将 http 和 https 的默认打开命令修改为指向受控浏览器，
    并传入 --user-data-dir 与 --profile-directory 参数，确保与 Playwright 上下文一致。
    """
    # 构造命令字符串，注意外层双引号包裹路径，内层保留转义
    command = f'"{browser_path}" --user-data-dir="{user_data_dir}" --profile-directory=Default -- "%1"'
    for protocol in ("http", "https"):
        try:
            key_path = f"Software\\Classes\\{protocol}\\shell\\open\\command"
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE) as key:
                winreg.SetValueEx(key, None, 0, winreg.REG_SZ, command)
        except Exception as e:
            print(f"[WARN] 设置 {protocol} 默认浏览器失败: {e}")


def build_inject_script(answer_config_json: str) -> str:
    """
    构造需要注入页面的 JavaScript 自执行函数字符串。
    该字符串会被 page.add_init_script() 在每个页面加载前注入，包含完整的自动填写逻辑。
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
        "                        }, 10);\n"
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


def url_matches_any(url: str, patterns: list) -> bool:
    """
    简单的通配符匹配函数，判断 URL 是否匹配预设规则列表。
    支持 * 作为通配符匹配任意字符。
    """
    for pat in patterns:
        if fnmatch(url, pat):
            return True
    return False


def load_answer_config(config_path: str | None) -> list:
    """
    加载答案配置。如果指定了外部 JSON 文件则读取，否则使用默认配置。
    """
    if config_path and os.path.exists(config_path):
        with open(config_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, list):
                return data
    return DEFAULT_ANSWER_CONFIG


class AutoFillApp:
    """
    GUI 控制面板，用于启动和停止自动填写服务。
    新增注册表接管与恢复、窗口关闭拦截功能。
    """

    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("自动表单填写工具")
        self.root.geometry("520x420")
        self.root.resizable(False, False)

        # 运行状态
        self.is_running = False
        self.browser_thread = None
        self.stop_event = threading.Event()
        self.browser_context = None

        # 配置变量
        self.browser_var = tk.StringVar(value="edge")
        self.config_var = tk.StringVar(value="")

        # 新增：注册表备份与浏览器路径
        self.registry_backup = None
        self.browser_path = None

        self._build_ui()

        # 新增：拦截窗口关闭事件，服务运行期间禁止关闭
        self.root.protocol("WM_DELETE_WINDOW", self._on_closing)

    def _build_ui(self):
        # 标题
        title = tk.Label(self.root, text="🚀 自动表单填写工具", font=("Microsoft YaHei", 16, "bold"))
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
        self.log_box.configure(state=tk.NORMAL)
        self.log_box.insert(tk.END, f"[{time.strftime('%H:%M:%S')}] {message}\n")
        self.log_box.see(tk.END)
        self.log_box.configure(state=tk.DISABLED)

    def _on_closing(self):
        """
        窗口关闭拦截：若服务正在运行，弹出警告阻止关闭；否则正常退出。
        """
        if self.is_running:
            messagebox.showwarning("警告", "请先停止服务再关闭窗口！")
        else:
            self.root.destroy()

    def _start_service(self):
        if self.is_running:
            return

        # 新增：查找浏览器路径，失败则弹窗提示并终止启动
        browser_choice = self.browser_var.get()
        self.browser_path = find_browser_path(browser_choice)
        if not self.browser_path:
            messagebox.showerror("错误", f"未找到 {browser_choice.capitalize()} 浏览器！\n请确认已安装。")
            return

        self.is_running = True
        self.stop_event.clear()

        self.start_btn.configure(state=tk.DISABLED)
        self.stop_btn.configure(state=tk.NORMAL)
        self.status_label.configure(text="状态: 运行中", fg="green")

        self._log("正在启动浏览器服务...")

        # 新增：备份注册表并临时接管默认浏览器
        try:
            self.registry_backup = backup_registry()
            user_data_dir = os.path.abspath(f"./user_data_{browser_choice}")
            os.makedirs(user_data_dir, exist_ok=True)
            set_as_default(self.browser_path, user_data_dir)
            self._log("已临时接管默认浏览器，外部链接将自动跳转至此窗口。")
        except Exception as e:
            self._log(f"注册表操作失败: {e}")
            # 若接管失败，继续启动浏览器服务，不影响核心功能

        self.browser_thread = threading.Thread(target=self._browser_worker, daemon=True)
        self.browser_thread.start()

    def _stop_service(self):
        if not self.is_running:
            return
        self._log("正在停止服务...")
        self.stop_event.set()
        self.is_running = False

        self.start_btn.configure(state=tk.NORMAL)
        self.stop_btn.configure(state=tk.DISABLED)
        self.status_label.configure(text="状态: 已停止", fg="gray")

        # 新增：恢复注册表默认浏览器设置
        if self.registry_backup is not None:
            try:
                restore_registry(self.registry_backup)
                self._log("已恢复系统默认浏览器。")
            except Exception as e:
                self._log(f"恢复注册表失败: {e}")
            finally:
                self.registry_backup = None

        if self.browser_context:
            try:
                self.browser_context.close()
            except Exception:
                pass
            self.browser_context = None

        self._log("服务已停止。")

    def _browser_worker(self):
        """
        在独立线程中运行 Playwright 浏览器，避免阻塞 GUI 主线程。
        """
        try:
            browser_choice = self.browser_var.get()
            config_path = self.config_var.get() or None

            answer_config = load_answer_config(config_path)
            if config_path:
                self._log(f"已加载外部配置: {config_path}")
            else:
                self._log("使用内置默认配置")

            answer_config_json = json.dumps(answer_config, ensure_ascii=False, indent=2)
            init_script = build_inject_script(answer_config_json)

            channel = "msedge" if browser_choice == "edge" else "chrome"
            user_data_dir = os.path.abspath(f"./user_data_{browser_choice}")
            os.makedirs(user_data_dir, exist_ok=True)

            self._log(f"启动 {browser_choice.capitalize()} 浏览器...")
            self._log("请正常浏览网页，遇到匹配表单页面时会自动填写。")

            with sync_playwright() as p:
                browser = p.chromium.launch_persistent_context(
                    user_data_dir=user_data_dir,
                    channel=channel,
                    headless=False,
                    args=[
                        "--disable-blink-features=AutomationControlled",
                        "--disable-infobars",
                        "--window-size=1366,768",
                        # 新增：显式指定 profile-directory，与注册表命令保持一致
                        "--profile-directory=Default",
                    ],
                    viewport={"width": 1366, "height": 768},
                    locale="zh-CN",
                )
                self.browser_context = browser

                pages = browser.pages
                page = pages[0] if pages else browser.new_page()
                page.add_init_script(init_script)

                def on_page(new_page):
                    new_page.add_init_script(init_script)
                    self._log(f"新页面: {new_page.url}")

                browser.on("page", on_page)

                # 持续运行直到收到停止信号
                while not self.stop_event.is_set():
                    time.sleep(0.5)

                browser.close()
                self._log("浏览器已关闭。")
        except Exception as e:
            self._log(f"错误: {e}")
        finally:
            self.is_running = False
            self.browser_context = None
            # 在主线程中更新 UI
            self.root.after(0, self._on_worker_finished)

    def _on_worker_finished(self):
        self.start_btn.configure(state=tk.NORMAL)
        self.stop_btn.configure(state=tk.DISABLED)
        self.status_label.configure(text="状态: 已停止", fg="gray")
        self._log("服务线程已结束。")


def main():
    parser = argparse.ArgumentParser(description="自动表单填写工具 —— 基于 Playwright")
    parser.add_argument("--browser", choices=["chrome", "edge"], default="edge", help="选择浏览器，默认 edge")
    parser.add_argument("--config", default=None, help="指定外部答案配置文件路径（JSON 格式）")
    parser.add_argument("--no-gui", action="store_true", help="不使用 GUI，直接以命令行模式启动")
    args = parser.parse_args()

    if args.no_gui:
        # 命令行模式（原逻辑，不做注册表接管）
        answer_config = load_answer_config(args.config)
        answer_config_json = json.dumps(answer_config, ensure_ascii=False, indent=2)
        init_script = build_inject_script(answer_config_json)

        channel = "msedge" if args.browser == "edge" else "chrome"
        user_data_dir = os.path.abspath(f"./user_data_{args.browser}")
        os.makedirs(user_data_dir, exist_ok=True)

        print(f"🚀 正在启动 {args.browser.capitalize()} 浏览器...")
        print("⏳ 自动填写服务已就绪，请正常浏览网页。遇到匹配的表单页面时会自动填写。")
        print("💡 提示：页面右下角会出现「📝 自动填写表单」按钮，可随时手动触发重填。")
        print("🛠️  在浏览器控制台输入 dumpFormFields() 可查看字段识别结果。")
        print("=" * 60)

        with sync_playwright() as p:
            browser = p.chromium.launch_persistent_context(
                user_data_dir=user_data_dir,
                channel=channel,
                headless=False,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--disable-infobars",
                    "--window-size=1366,768",
                ],
                viewport={"width": 1366, "height": 768},
                locale="zh-CN",
            )
            pages = browser.pages
            page = pages[0] if pages else browser.new_page()
            page.add_init_script(init_script)

            def on_page(new_page):
                new_page.add_init_script(init_script)
                print(f"📑 新页面打开: {new_page.url}")

            browser.on("page", on_page)

            try:
                while True:
                    time.sleep(1)
                    if browser.pages is None:
                        break
            except KeyboardInterrupt:
                print("\n👋 收到中断信号，正在关闭浏览器...")
            finally:
                browser.close()
                print("🛑 浏览器已关闭，程序退出。")
    else:
        # GUI 模式
        root = tk.Tk()
        app = AutoFillApp(root)

        # 新增：atexit 兜底，程序异常退出时尝试恢复注册表
        def _atexit_restore():
            if app.registry_backup is not None:
                try:
                    restore_registry(app.registry_backup)
                    print("[atexit] 已恢复系统默认浏览器设置。")
                except Exception as e:
                    print(f"[atexit] 恢复注册表失败: {e}")

        atexit.register(_atexit_restore)

        root.mainloop()


if __name__ == "__main__":
    main()
