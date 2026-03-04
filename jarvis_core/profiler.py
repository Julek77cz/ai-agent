"""Hardware profiling for JARVIS - detects CPU, RAM, and VRAM resources."""
import logging
import subprocess
from dataclasses import dataclass

logger = logging.getLogger("JARVIS.CORE.PROFILER")


@dataclass
class HardwareProfile:
    ram_gb: float
    cpu_cores: int
    vram_gb: float
    gpu_name: str
    gpu_detected: bool

    def __str__(self) -> str:
        if self.gpu_detected:
            return (
                f"CPU={self.cpu_cores} cores, RAM={self.ram_gb:.1f}GB, "
                f"GPU={self.gpu_name} VRAM={self.vram_gb:.1f}GB"
            )
        return f"CPU={self.cpu_cores} cores, RAM={self.ram_gb:.1f}GB, GPU=none"


class SystemProfiler:
    def detect_cpu(self) -> int:
        try:
            import psutil
            cores = psutil.cpu_count(logical=False) or psutil.cpu_count(logical=True) or 1
            return cores
        except ImportError:
            import os
            return os.cpu_count() or 1

    def detect_ram(self) -> float:
        try:
            import psutil
            return psutil.virtual_memory().total / (1024 ** 3)
        except ImportError:
            return 0.0

    def detect_vram(self) -> tuple[float, str, bool]:
        try:
            result = subprocess.run(
                ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0 and result.stdout.strip():
                line = result.stdout.strip().splitlines()[0]
                parts = line.split(",")
                if len(parts) == 2:
                    gpu_name = parts[0].strip()
                    vram_mb = float(parts[1].strip())
                    return vram_mb / 1024.0, gpu_name, True
        except (FileNotFoundError, subprocess.TimeoutExpired, ValueError, OSError):
            pass
        return 0.0, "", False

    def profile(self) -> HardwareProfile:
        cpu_cores = self.detect_cpu()
        ram_gb = self.detect_ram()
        vram_gb, gpu_name, gpu_detected = self.detect_vram()
        return HardwareProfile(
            ram_gb=ram_gb,
            cpu_cores=cpu_cores,
            vram_gb=vram_gb,
            gpu_name=gpu_name,
            gpu_detected=gpu_detected,
        )
