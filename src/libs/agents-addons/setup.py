# setup.py
from setuptools import setup, find_packages

setup(
    name="agent_addons",
    version="0.1.0",
    description="SDK for ArangoDB, Embeddings DB (Weaviate/Pinecone), and Arango-to-Embeddings ingestion.",
    author="",
    author_email="Opencyberspace.org",
    url="",  
    packages=find_packages(exclude=("tests", "examples")),
    python_requires=">=3.8",
    install_requires=[
        "python-arango",
        "requests",
        "weaviate-client",
        "pinecone-client",
        "boto3",
        "redis"
    ],
    extras_require={
        "s3": ["boto3"],
        "ml": ["sentence-transformers", "torch"],
        "dev": ["black", "flake8", "pytest"],
    },
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License", 
        "Operating System :: OS Independent",
    ],
    entry_points={
        "console_scripts": [
        ]
    },
    include_package_data=True,
    zip_safe=False,
)
