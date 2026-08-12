#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
project_root="$(cd "${script_dir}/.." && pwd)"
python_bin="${MOS_AGONDEV_PYTHON:-${project_root}/.venv/bin/python}"
profile_dir="${MOS_AGONDEV_EMULATOR_PROFILE:-${project_root}/emulator}"
fab_root="${MOS_AGONDEV_FAB_ROOT:-${project_root}/../../fab-agon-emulator}"

if [[ ! -x "${python_bin}" ]]; then
    printf 'Project Python is missing or not executable: %s\n' "${python_bin}" >&2
    exit 1
fi

# These inputs define the qualified stock profile and cannot be overridden by
# forwarded convenience arguments. Add a separate launcher when custom MOS or
# VDP qualification begins.
for emulator_arg in "$@"; do
    case "${emulator_arg}" in
        --firmware|--firmware=*|--mos|--mos=*|--vdp|--vdp=*|\
        --sdcard|--sdcard=*|--sdcard-img|--sdcard-img=*|\
        --renderer|--renderer=*|--verbose|-z|--zero)
            printf 'run_emulator.sh manages this option: %s\n' \
                "${emulator_arg}" >&2
            exit 2
            ;;
    esac
done

"${python_bin}" "${script_dir}/verify_emulator.py" \
    --profile "${profile_dir}" \
    --fab-root "${fab_root}" \
    --quiet

cd "${profile_dir}"
export SDL_VIDEODRIVER="${SDL_VIDEODRIVER:-wayland}"
exec ./fab-agon-emulator \
    --renderer sw \
    --firmware platform \
    --sdcard ./sdcard \
    --verbose \
    -z \
    "$@"
