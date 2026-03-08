# Repository Reorganization

## Overview
This document describes the repository reorganization completed to improve project structure and maintainability.

## Changes Made

### 1. Documentation Directory (`docs/`)
All documentation files have been moved to the `docs/` directory:
- `IMPLEMENTATION_COMPLETE.md` → `docs/IMPLEMENTATION_COMPLETE.md`
- `INSTALL.md` → `docs/INSTALL.md`
- `JARVIS_V20_SUMMARY.md` → `docs/JARVIS_V20_SUMMARY.md`
- `README_VERSIONING.md` → `docs/README_VERSIONING.md`
- `SETUP_CHANGES.md` → `docs/SETUP_CHANGES.md`

### 2. Scripts Directory (`scripts/`)
All installation and execution scripts have been moved to the `scripts/` directory:
- `quick-setup.sh` → `scripts/quick-setup.sh`
- `run.bat` → `scripts/run.bat`
- `run.sh` → `scripts/run.sh`
- `setup.bat` → `scripts/setup.bat`
- `setup.py` → `scripts/setup.py`
- `setup.sh` → `scripts/setup.sh`
- `start_jarvis.bat` → `scripts/start_jarvis.bat`
- `start_jarvis_dev.bat` → `scripts/start_jarvis_dev.bat`
- `start_jarvis_v20.bat` → `scripts/start_jarvis_v20.bat`
- `start_jarvis_v20.sh` → `scripts/start_jarvis_v20.sh`

### 3. Tests Directory (`tests/`)
All test files have been moved to the `tests/` directory:
- `test_scenarios.py` → `tests/test_scenarios.py`

## Path Updates

### Documentation References
The `docs/INSTALL.md` file has been updated to reference the new script locations:
- All script paths now include the `scripts/` prefix
- File structure documentation updated to reflect new directory layout

### Test File
The `tests/test_scenarios.py` file has been updated:
- Usage instructions updated to reference the new path
- Python path imports adjusted to work from the new location

## New Directory Structure

```
jarvis-project/
├── docs/                          # All documentation
│   ├── IMPLEMENTATION_COMPLETE.md
│   ├── INSTALL.md
│   ├── JARVIS_V20_SUMMARY.md
│   ├── README_VERSIONING.md
│   ├── REORGANIZATION.md
│   └── SETUP_CHANGES.md
├── scripts/                       # All installation and execution scripts
│   ├── quick-setup.sh
│   ├── run.bat
│   ├── run.sh
│   ├── setup.bat
│   ├── setup.py
│   ├── setup.sh
│   ├── start_jarvis.bat
│   ├── start_jarvis_dev.bat
│   ├── start_jarvis_v20.bat
│   └── start_jarvis_v20.sh
├── tests/                         # All test files
│   └── test_scenarios.py
├── jarvis/                        # Core package
├── jarvis_config/                 # Configuration
├── jarvis_core/                   # Core functionality
├── jarvis_data/                   # Data storage
├── jarvis_memory/                 # Memory system
├── jarvis_reasoning/              # Reasoning engine
├── jarvis_tools/                  # Tool definitions
├── jarvis_v19/                    # Version 19
├── jarvis_v20/                    # Version 20
├── start.py                       # Universal launcher
├── jarvis_v20.py                  # V20 entry point
└── requirements*.txt               # Dependencies
```

## Usage After Reorganization

### Running Setup
```bash
# Windows
scripts/setup.bat

# Linux/Mac
chmod +x scripts/setup.sh
./scripts/setup.sh
```

### Running JARVIS
```bash
# Windows
scripts/run.bat

# Linux/Mac
chmod +x scripts/run.sh
./scripts/run.sh
```

### Running Tests
```bash
cd /home/engine/project
python tests/test_scenarios.py
```

### Using start.py (Recommended)
The universal launcher `start.py` remains in the root and continues to work without changes:
```bash
python start.py --v20
python start.py --v19
```

## Benefits

1. **Cleaner Root Directory**: Reduced clutter in the project root
2. **Better Organization**: Logical grouping of files by type
3. **Easier Navigation**: Clear separation of concerns
4. **Professional Structure**: Follows common Python project conventions
5. **Maintainability**: Easier to find and manage documentation, scripts, and tests

## Backward Compatibility

- The `start.py` universal launcher continues to work from the root directory
- Scripts can still be executed from their new locations
- Test imports have been updated to work correctly from the new location
- All documentation paths have been updated where necessary

## Migration Guide

If you have existing references to the old paths, update them as follows:

### Old → New
- `./setup.sh` → `./scripts/setup.sh`
- `./run.sh` → `./scripts/run.sh`
- `./setup.bat` → `./scripts/setup.bat`
- `./run.bat` → `./scripts/run.bat`
- `python test_scenarios.py` → `python tests/test_scenarios.py`
- Documentation files are now accessed via `docs/` prefix
