"""
Progress Tracker - Real-Time Sync Progress Reporting
====================================================

Tracks and broadcasts sync progress for WebSocket updates during long batch operations.

Usage:
    tracker = ProgressTracker(total_files=1000, websocket_callback=broadcast_fn)
    for i, file in enumerate(files):
        tracker.update(i, str(file))
        # Process file...
"""

from collections.abc import Callable
from datetime import datetime
from typing import Any


class ProgressTracker:
    """Tracks and broadcasts sync progress."""

    def __init__(
        self,
        total_files: int,
        websocket_callback: Callable[[dict[str, Any]], None] | None = None,
    ):
        """
        Initialize progress tracker.

        Args:
            total_files: Total number of files to process
            websocket_callback: Optional callback to broadcast progress updates
        """
        self.total_files = total_files
        self.current_file_index = 0
        self.current_file_path = ""
        self.websocket_callback = websocket_callback
        self.start_time = datetime.now()

    def update(self, file_index: int, file_path: str) -> None:
        """
        Update progress and broadcast to WebSocket.

        Args:
            file_index: Current file index (0-based)
            file_path: Path to current file being processed
        """
        self.current_file_index = file_index
        self.current_file_path = file_path

        if self.websocket_callback:
            progress_data = {
                "current": file_index,
                "total": self.total_files,
                "percentage": round((file_index / self.total_files) * 100, 1) if self.total_files > 0 else 0,
                "current_file": file_path,
                "eta_seconds": self._calculate_eta(),
            }
            self.websocket_callback(progress_data)

    def _calculate_eta(self) -> int:
        """
        Estimate time remaining based on current rate.

        Returns:
            Estimated seconds remaining
        """
        elapsed = (datetime.now() - self.start_time).total_seconds()
        if self.current_file_index == 0:
            return 0
        rate = self.current_file_index / elapsed
        remaining = self.total_files - self.current_file_index
        return int(remaining / rate) if rate > 0 else 0


__all__ = ["ProgressTracker"]
