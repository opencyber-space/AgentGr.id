# setup.py
from pathlib import Path
from setuptools import setup, find_packages

PACKAGE_NAME = "agent_core_libs"
ROOT = Path(__file__).parent
README = (ROOT / "README.md")

long_description = ""
if README.exists():
    long_description = README.read_text(encoding="utf-8")

setup(
    name=PACKAGE_NAME,
    version="0.1.0",
    description="Core libraries for agent frameworks: storage, cache, SQL helper, config, metrics, and web scraping SDK.",
    long_description=long_description or "Core libs: S3 storage, Redis cache, SQL helper, config manager, metrics, Scrapy SDK.",
    long_description_content_type="text/markdown",
    author="Your Name",
    author_email="you@example.com",
    url="https://github.com/your-org/agent_core_libs",
    license="MIT",

    packages=find_packages(exclude=("tests", "examples", "docs")),
    include_package_data=True,
    python_requires=">=3.9",

    # Libraries actually used in your modules so far
    install_requires=[
        "boto3>=1.34.0",            # storage.py (S3)
        "redis>=5.0.0",             # common_cache.py, config.py, metrics.py
        "sqlalchemy>=2.0.0",        # sql_inface.py
        "prometheus-client>=0.20.0", # metrics.py,
        "scrapy"
    ],

    # Optional, nice-to-have extras
    extras_require={
        # Hardware metrics for AgentsMetrics (optional)
        "metrics-hw": ["psutil>=5.9.0"],
        # Web scraping SDK (web_scrapping.py) if you’re using Scrapy
        "scraping": ["scrapy>=2.11.0"],
        # Full set
        "all": ["psutil>=5.9.0", "scrapy>=2.11.0"],
    },

    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Topic :: Software Development :: Libraries",
        "Topic :: Internet :: WWW/HTTP",
        "Topic :: Database",
        "Topic :: System :: Monitoring",
    ],

    project_urls={
        "Source": "https://github.com/your-org/agent_core_libs",
        "Issues": "https://github.com/your-org/agent_core_libs/issues",
    },
)
