class SalesAgentException(Exception):
    """Base exception for sales agent"""
    pass

class ConfigurationError(SalesAgentException):
    """Raised when configuration is invalid"""
    pass

class RateLimitError(SalesAgentException):
    """Raised when rate limit is exceeded"""
    pass

class ProxyError(SalesAgentException):
    """Raised when proxy fails"""
    pass