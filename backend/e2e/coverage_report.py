"""The API's code coverage so far, for the end-to-end run's report.

The e2e image and CI start the API with ``coverage run``, so it records which lines the
Playwright tests made it run.
"""

import base64
import tempfile
from pathlib import Path

import coverage
from pydantic import BaseModel


class CoverageFile(BaseModel):
    path: str
    # Base64, since the HTML report includes images.
    content: str


class CoverageReport(BaseModel):
    percent_covered: float
    files: list[CoverageFile]


def current_measurement() -> coverage.Coverage | None:
    """The measurement the API was started under, if any."""
    return coverage.Coverage.current()


def report(measurement: coverage.Coverage) -> CoverageReport:
    """An HTML report and an LCOV file of everything measured so far."""
    measurement.save()
    with tempfile.TemporaryDirectory() as folder:
        output = Path(folder)
        percent = measurement.html_report(directory=str(output / "html"))
        measurement.lcov_report(outfile=str(output / "lcov.info"))
        files = [
            CoverageFile(
                path=path.relative_to(output).as_posix(),
                content=base64.b64encode(path.read_bytes()).decode(),
            )
            for path in sorted(output.rglob("*"))
            if path.is_file()
        ]
    return CoverageReport(percent_covered=round(percent, 2), files=files)
