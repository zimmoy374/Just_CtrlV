from __future__ import annotations

from typing import Any, Iterable


CAPABILITY_PROFILES = {
    "work": {
        "label": "工作接力",
        "description": "默认档位，只读取公开工作上下文和正式知识，不读取个人资料、私密或敏感证据。",
        "allowedCapabilities": [],
    },
    "profile": {
        "label": "个人资料",
        "description": "允许读取用户确认过的 profile fact，用于偏好、身份、长期习惯等个性化上下文。",
        "allowedCapabilities": ["profile_memory"],
    },
    "private": {
        "label": "私密记忆",
        "description": "允许读取标记为 private 的本地证据摘录，适合用户明确授权的可信本地 agent。",
        "allowedCapabilities": ["private_memory"],
    },
    "sensitive": {
        "label": "敏感记忆",
        "description": "允许读取 private 和 sensitive 证据摘录，只应给用户完全信任的本地 agent 使用。",
        "allowedCapabilities": ["private_memory", "sensitive_memory"],
    },
    "trusted": {
        "label": "完全可信本地 agent",
        "description": "允许读取所有本地 agent 能力档位，但仍不能直接写入正式长期记忆。",
        "allowedCapabilities": ["external_agent_allowed", "profile_memory", "private_memory", "sensitive_memory"],
    },
}


def list_capability_profiles() -> dict[str, dict[str, Any]]:
    return {
        name: {
            "label": str(profile["label"]),
            "description": str(profile["description"]),
            "allowedCapabilities": list(profile["allowedCapabilities"]),
        }
        for name, profile in CAPABILITY_PROFILES.items()
    }


def resolve_capabilities(profile: str | None = None, requested: Iterable[str] | None = None) -> list[str]:
    profile_name = (profile or "work").strip() or "work"
    if profile_name not in CAPABILITY_PROFILES:
        raise ValueError(f"未知 capability profile：{profile_name}")
    allowed = set(CAPABILITY_PROFILES[profile_name]["allowedCapabilities"])
    if requested is None:
        return sorted(allowed)
    requested_set = {str(item).strip() for item in requested if str(item).strip()}
    return sorted(allowed & requested_set)
