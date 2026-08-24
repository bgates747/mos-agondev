#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
project_root="$(cd "${script_dir}/.." && pwd)"
python_bin="${MOS_AGONDEV_PYTHON:-${project_root}/.venv/bin/python}"
profile_dir="${MOS_AGONDEV_EMULATOR_PROFILE:-${project_root}/emulator}"
fab_root="${MOS_AGONDEV_FAB_ROOT:-${project_root}/fab-agon-emulator}"

if [[ ! -x "${python_bin}" ]]; then
    printf 'Project Python is missing or not executable: %s\n' "${python_bin}" >&2
    exit 1
fi

"${python_bin}" "${script_dir}/verify_emulator.py" \
    --profile "${profile_dir}" \
    --fab-root "${fab_root}" \
    --quiet

cd "${profile_dir}"
exec ./fab-agon-emulator "$@"
