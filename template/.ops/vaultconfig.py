# -*- coding: utf-8 -*-
"""讀取 .ops/config.json。所有與環境有關的值都集中在這裡，腳本本身不寫死路徑。"""
import os, json

OPS = os.path.dirname(os.path.abspath(__file__))
VAULT = os.path.dirname(OPS)
_PATH = os.path.join(OPS, "config.json")

_DEFAULTS = {
    "gitlab_api": "https://gitlab.com/api/v4",
    "gitlab_group": "",
    "github_owner": "",
    "source_root": "",
    "since_days": 30,
    "container_dirs": [],
}

def load():
    cfg = dict(_DEFAULTS)
    if os.path.exists(_PATH):
        with open(_PATH, encoding="utf-8") as f:
            cfg.update({k: v for k, v in json.load(f).items() if not k.startswith("_")})
    # vault 一律由檔案位置推導，config 裡的 vault 只給 PowerShell 用
    cfg["vault"] = VAULT
    cfg["source_root"] = (cfg.get("source_root") or "").replace("\\", "/").rstrip("/")
    return cfg

CFG = load()
