from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("job-radar")
except PackageNotFoundError:  # executando a partir do código-fonte sem instalação
    __version__ = "0.0.0"
