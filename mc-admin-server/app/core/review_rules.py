"""
命令审核规则配置。
规则引擎根据此配置判断命令风险等级。
"""

from app.models.review import RiskLevel

# 命令 → 基础风险等级映射
COMMAND_RISK_MAP: dict[str, RiskLevel] = {
    # 低危
    "list":     RiskLevel.LOW,
    "say":      RiskLevel.LOW,
    "time":     RiskLevel.LOW,
    "weather":  RiskLevel.LOW,
    "save-all": RiskLevel.LOW,

    # 中危
    "op":        RiskLevel.MEDIUM,
    "deop":      RiskLevel.MEDIUM,
    "kick":      RiskLevel.MEDIUM,
    "whitelist": RiskLevel.MEDIUM,
    "give":      RiskLevel.MEDIUM,
    "tp":        RiskLevel.MEDIUM,
    "gamemode":  RiskLevel.MEDIUM,

    # 高危
    "ban":    RiskLevel.HIGH,
    "pardon": RiskLevel.HIGH,
    "stop":   RiskLevel.HIGH,
}

# 特殊工具（非原始命令）的风险等级
TOOL_RISK_MAP: dict[str, RiskLevel | None] = {
    "get_status":      RiskLevel.LOW,
    "broadcast":       RiskLevel.LOW,
    "execute_command":  None,      # 取决于具体命令，需解析
    "kick_player":     RiskLevel.MEDIUM,
    "op_player":       RiskLevel.MEDIUM,
    "deop_player":     RiskLevel.MEDIUM,
    "restart_server":  RiskLevel.HIGH,
}

# 频率检测阈值
RATE_LIMITS = {
    "burst_window_seconds": 30,
    "burst_threshold": 3,
    "multi_target_threshold": 3,
}

# 强制升级为高危的模式
FORCE_HIGH_PATTERNS = [
    r"@a",
    r"@e",
]

# give 命令数量异常阈值
GIVE_AMOUNT_THRESHOLD = 1000
