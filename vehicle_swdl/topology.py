from __future__ import annotations

from .models import FormatError, SoftwareImage


def dependency_order(images: tuple[SoftwareImage, ...] | list[SoftwareImage]) -> list[SoftwareImage]:
    by_id = {image.ecu_id: image for image in images}
    for image in images:
        unknown = sorted(set(image.depends_on) - by_id.keys())
        if unknown:
            raise FormatError(
                f"Image {image.ecu_id!r} depends on unknown ECU(s): {', '.join(unknown)}"
            )
        if image.ecu_id in image.depends_on:
            raise FormatError(f"Image {image.ecu_id!r} cannot depend on itself")

    ordered: list[SoftwareImage] = []
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(ecu_id: str) -> None:
        if ecu_id in visited:
            return
        if ecu_id in visiting:
            raise FormatError(f"Cyclic SWDL dependency includes ECU {ecu_id!r}")
        visiting.add(ecu_id)
        image = by_id[ecu_id]
        for dependency in image.depends_on:
            visit(dependency)
        visiting.remove(ecu_id)
        visited.add(ecu_id)
        ordered.append(image)

    for image in images:
        visit(image.ecu_id)
    return ordered
