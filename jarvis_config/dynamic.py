"""Dynamic hardware-aware configuration for JARVIS."""
import logging

logger = logging.getLogger("JARVIS.CONFIG.DYNAMIC")


def apply_hardware_scaling() -> tuple:
    from jarvis_core.profiler import SystemProfiler
    import jarvis_config as _cfg

    hw_profile = SystemProfiler().profile()

    if hw_profile.ram_gb < 16 or hw_profile.cpu_cores < 6:
        swarm_agents = 2
    else:
        swarm_agents = 4

    if not hw_profile.gpu_detected or hw_profile.vram_gb < 8:
        context_limit = 2048
    else:
        context_limit = 4096

    _cfg.SWARM_MAX_AGENTS = swarm_agents
    _cfg.HW_OPTIONS["num_ctx"] = context_limit

    return hw_profile, swarm_agents, context_limit
