class PipelineError(Exception):
    """Base exception for all pipeline errors."""
    pass

class AntiBotChallengeError(PipelineError):
    """Raised when an anti-bot challenge (e.g., Cloudflare) is encountered."""
    pass

class NetworkFetchError(PipelineError):
    """Raised when a network fetch fails."""
    pass
