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

# New Browser-related Exceptions
class BrowserException(SalesAgentException):
    """Base exception for browser operations"""
    pass

class ElementNotFoundException(BrowserException):
    """Raised when an element cannot be found on the page"""
    def __init__(self, selector: str, message: str = None):
        self.selector = selector
        self.message = message or f"Element not found with selector: {selector}"
        super().__init__(self.message)

class ProxyConnectionError(BrowserException):
    """Raised when there are issues with proxy connection"""
    def __init__(self, proxy_host: str, message: str = None):
        self.proxy_host = proxy_host
        self.message = message or f"Failed to connect using proxy: {proxy_host}"
        super().__init__(self.message)

class SessionError(BrowserException):
    """Raised when there are issues with browser session management"""
    def __init__(self, context_id: str = None, message: str = None):
        self.context_id = context_id
        self.message = message or f"Session error occurred{f' for context: {context_id}' if context_id else ''}"
        super().__init__(self.message)

class BrowserPoolError(BrowserException):
    """Raised when there are issues with browser pool management"""
    pass

class NavigationError(BrowserException):
    """Raised when navigation fails or times out"""
    def __init__(self, url: str, message: str = None):
        self.url = url
        self.message = message or f"Navigation failed for URL: {url}"
        super().__init__(self.message)

class ScreenshotError(BrowserException):
    """Raised when screenshot capture or storage fails"""
    def __init__(self, path: str = None, message: str = None):
        self.path = path
        self.message = message or f"Screenshot operation failed{f' for path: {path}' if path else ''}"
        super().__init__(self.message)

class ElementInteractionError(BrowserException):
    """Raised when interaction with an element fails"""
    def __init__(self, selector: str, action: str, message: str = None):
        self.selector = selector
        self.action = action
        self.message = message or f"Failed to {action} element with selector: {selector}"
        super().__init__(self.message)

class TimeoutError(BrowserException):
    """Raised when an operation times out"""
    def __init__(self, operation: str, timeout: int, message: str = None):
        self.operation = operation
        self.timeout = timeout
        self.message = message or f"Operation '{operation}' timed out after {timeout}ms"
        super().__init__(self.message)