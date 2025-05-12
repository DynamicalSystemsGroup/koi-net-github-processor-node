import logging
import os
import sys
import uvicorn

# Setup logging first
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger(__name__)

# Check required directories exist
def ensure_directories(config):
    """Ensure all required directories exist."""
    try:
        os.makedirs(os.path.dirname(config.index_db_path), exist_ok=True)
        return True
    except Exception as e:
        logger.error(f"Failed to create required directories: {e}")
        return False

from .core import node

# Validate configuration
if not node.config.server:
    logger.error("Server configuration is missing. Please check config.yaml")
    sys.exit(1)

# Ensure directories exist
if not ensure_directories(node.config):
    logger.error("Failed to initialize directories. Exiting.")
    sys.exit(1)

logger.info(f"Starting Uvicorn server on {node.config.server.host}:{node.config.server.port} with root_path {node.config.server.path}")
uvicorn.run(
    "github_processor_node.server:app",
    host=node.config.server.host,
    port=node.config.server.port,
)
