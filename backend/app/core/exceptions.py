"""异常体系"""

class TripPlannerAgentsException(Exception):
    """基础异常类"""
    pass

class LLMException(TripPlannerAgentsException):
    """LLM相关异常"""
    pass

class AgentException(TripPlannerAgentsException):
    """Agent相关异常"""
    pass

class ConfigException(TripPlannerAgentsException):
    """配置相关异常"""
    pass

class ToolException(TripPlannerAgentsException):
    """工具相关异常"""
    pass
