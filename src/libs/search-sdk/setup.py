# setup.py
from pathlib import Path
from setuptools import setup, find_packages

PACKAGE_NAME = "agents_search"
ROOT = Path(__file__).parent
README = (ROOT / "README.md")

long_description = ""
if README.exists():
    long_description = README.read_text(encoding="utf-8")

setup(
    name=PACKAGE_NAME,
    version="0.1.0",
    description="Search and embeddings utilities for agent frameworks: OpenAI, AIOS, and custom selector/embedding managers.",
    long_description=long_description or "Search and embeddings utils: OpenAI selector, AIOS integration, managers for agents.",
    long_description_content_type="text/markdown",
    author="Your Name",
    author_email="you@example.com",
    url="https://github.com/your-org/agents_search",
    license="MIT",

    packages=find_packages(exclude=("tests", "examples", "docs")),
    include_package_data=True,

    install_requires=[
        "openai",     
        "requests"
    ],

    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Topic :: Software Development :: Libraries",
        "Topic :: Scientific/Engineering :: Artificial Intelligence",
    ],

    project_urls={
        "Source": "https://github.com/your-org/agents_search",
        "Issues": "https://github.com/your-org/agents_search/issues",
    },
)
