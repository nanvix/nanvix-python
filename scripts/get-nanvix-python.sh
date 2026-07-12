#!/bin/bash
# shellcheck shell=bash

# Copyright(c) The Maintainers of Nanvix.
# Licensed under the MIT License.

# Description: Downloads the latest Nanvix Python runtime from GitHub releases.
# This script uses only tools commonly available on Ubuntu systems by default.

set -euo pipefail

# Exit codes.
readonly EXIT_SUCCESS=0
readonly EXIT_FAILURE=1

# Configuration.
readonly GITHUB_REPO="nanvix/nanvix-python"
readonly GITHUB_API_URL="https://api.github.com/repos/${GITHUB_REPO}/releases/latest"
readonly CONNECT_TIMEOUT="${NANVIX_CONNECT_TIMEOUT:-30}"
readonly MAX_TIMEOUT="${NANVIX_MAX_TIMEOUT:-300}"
readonly FORCE_DOWNLOAD="${NANVIX_FORCE_DOWNLOAD:-false}"

# Print usage information.
usage() {
    local script_name
    script_name=$(basename "$0")
    echo "Usage: $script_name [options] [output_directory]"
    echo ""
    echo "Downloads the latest Nanvix Python runtime from GitHub releases."
    echo ""
    echo "Arguments:"
    echo "  output_directory  Directory to save downloaded files (default: current directory)"
    echo ""
    echo "Options:"
    echo "  -f, --force       Force download even if files already exist"
    echo "  -h, --help        Show this help message and exit"
    echo ""
    echo "Environment Variables:"
    echo "  GITHUB_TOKEN                GitHub token for authenticated API requests (5000 req/hr vs 60 unauthenticated)"
    echo "  GH_TOKEN                    Alternative to GITHUB_TOKEN (GitHub CLI convention)"
    echo "  NANVIX_CONNECT_TIMEOUT      Connection timeout in seconds (default: 30)"
    echo "  NANVIX_MAX_TIMEOUT          Maximum total timeout in seconds (default: 300)"
    echo "  NANVIX_FORCE_DOWNLOAD       Force download if 'true' (default: false)"
    echo ""
    echo "Examples:"
    echo "  $script_name /tmp/nanvix-python"
    echo "  $script_name --force /tmp/nanvix-python"
    echo "  curl -fsSL -o get-nanvix-python.sh https://raw.githubusercontent.com/nanvix/nanvix-python/main/scripts/get-nanvix-python.sh"
    echo "  bash get-nanvix-python.sh /tmp/nanvix-python"
}

# Print an error message and exit.
error() {
    echo "Error: $1" >&2
    exit "$EXIT_FAILURE"
}

# Print an informational message.
info() {
    echo "[INFO] $1"
}

# Print a warning message.
warn() {
    echo "[WARN] $1" >&2
}

# Check if a command exists.
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Determine which download tool to use.
get_download_tool() {
    if command_exists curl; then
        echo "curl"
    elif command_exists wget; then
        echo "wget"
    else
        error "Neither curl nor wget found. Please install one of them."
    fi
}

# Download a URL to stdout using available tools.
download_to_stdout() {
    local url="$1"
    local tool
    local exit_code
    tool=$(get_download_tool)

    case "$tool" in
        curl)
            local curl_args=(curl -sL --fail --max-redirs 5
                --connect-timeout "$CONNECT_TIMEOUT"
                --max-time "$MAX_TIMEOUT")
            if [[ -n "${GITHUB_TOKEN:-}" ]]; then
                curl_args+=(-H "Authorization: Bearer $GITHUB_TOKEN")
            elif [[ -n "${GH_TOKEN:-}" ]]; then
                curl_args+=(-H "Authorization: Bearer $GH_TOKEN")
            fi
            curl_args+=("$url")
            "${curl_args[@]}"
            exit_code=$?
            if (( exit_code != 0 )); then
                warn "curl failed with exit code $exit_code for URL: $url"
                return 1
            fi
            ;;
        wget)
            local wget_args=(wget -qO- --max-redirect=5
                --dns-timeout="$CONNECT_TIMEOUT"
                --connect-timeout="$CONNECT_TIMEOUT"
                --timeout="$MAX_TIMEOUT")
            if [[ -n "${GITHUB_TOKEN:-}" ]]; then
                wget_args+=("--header=Authorization: Bearer $GITHUB_TOKEN")
            elif [[ -n "${GH_TOKEN:-}" ]]; then
                wget_args+=("--header=Authorization: Bearer $GH_TOKEN")
            fi
            wget_args+=("$url")
            "${wget_args[@]}"
            exit_code=$?
            if (( exit_code != 0 )); then
                warn "wget failed with exit code $exit_code for URL: $url"
                return 1
            fi
            ;;
    esac
}

# Download a URL to a file using available tools.
download_to_file() {
    local url="$1"
    local output="$2"
    local tool
    local exit_code
    tool=$(get_download_tool)

    case "$tool" in
        curl)
            local curl_args=(curl -sL --fail --max-redirs 5
                --connect-timeout "$CONNECT_TIMEOUT"
                --max-time "$MAX_TIMEOUT")
            if [[ -n "${GITHUB_TOKEN:-}" ]]; then
                curl_args+=(-H "Authorization: Bearer $GITHUB_TOKEN")
            elif [[ -n "${GH_TOKEN:-}" ]]; then
                curl_args+=(-H "Authorization: Bearer $GH_TOKEN")
            fi
            curl_args+=(-o "$output" "$url")
            "${curl_args[@]}"
            exit_code=$?
            if (( exit_code != 0 )); then
                warn "curl failed with exit code $exit_code for URL: $url"
                return 1
            fi
            ;;
        wget)
            local wget_args=(wget -q --max-redirect=5
                --dns-timeout="$CONNECT_TIMEOUT"
                --connect-timeout="$CONNECT_TIMEOUT"
                --timeout="$MAX_TIMEOUT")
            if [[ -n "${GITHUB_TOKEN:-}" ]]; then
                wget_args+=("--header=Authorization: Bearer $GITHUB_TOKEN")
            elif [[ -n "${GH_TOKEN:-}" ]]; then
                wget_args+=("--header=Authorization: Bearer $GH_TOKEN")
            fi
            wget_args+=(-O "$output" "$url")
            "${wget_args[@]}"
            exit_code=$?
            if (( exit_code != 0 )); then
                warn "wget failed with exit code $exit_code for URL: $url"
                return 1
            fi
            ;;
    esac
}

# Download with retry.
download_with_retry() {
    local url="$1"
    local retries="${2:-3}"
    local attempt=1
    local result=""

    while (( attempt <= retries )); do
        result=$(download_to_stdout "$url" 2>/dev/null) && break
        warn "Download attempt $attempt/$retries failed."
        attempt=$((attempt + 1))
        sleep 2
    done

    if [[ -z "$result" ]]; then
        return 1
    fi

    echo "$result"
}

# Minimal JSON value extractor (no jq dependency).
extract_json_value() {
    local json="$1"
    local key="$2"
    echo "$json" | sed -n "s/.*\"${key}\"[[:space:]]*:[[:space:]]*\"\([^\"]*\)\".*/\1/p" | head -1
}

# Extract asset download URLs from release JSON.
extract_asset_urls() {
    local json="$1"
    echo "$json" | grep -o '"browser_download_url"[[:space:]]*:[[:space:]]*"[^"]*"' \
        | sed 's/"browser_download_url"[[:space:]]*:[[:space:]]*"\(.*\)"/\1/'
}

# Clean up partial downloads on failure.
cleanup() {
    if [[ -n "${CURRENT_DOWNLOAD:-}" ]] && [[ -f "$CURRENT_DOWNLOAD" ]]; then
        rm -f "$CURRENT_DOWNLOAD" 2>/dev/null
    fi
}

# Main function.
main() {
    local force_download="$FORCE_DOWNLOAD"
    local output_dir="."

    # Parse command line arguments.
    while [[ $# -gt 0 ]]; do
        case "$1" in
            -h|--help)
                usage
                exit "$EXIT_SUCCESS"
                ;;
            -f|--force)
                force_download="true"
                shift
                ;;
            -*)
                error "Unknown option: $1. Use --help for usage information."
                ;;
            *)
                if [[ "$output_dir" != "." ]]; then
                    error "Multiple output directories specified. Use --help for usage."
                fi
                output_dir="$1"
                shift
                ;;
        esac
    done

    # Validate and normalize output directory path.
    if [[ "$output_dir" == "../"* || "$output_dir" == *"/../"* || "$output_dir" == *"/.." ]]; then
        error "Invalid output directory path: contains path traversal component '..'."
    fi
    output_dir=$(realpath -m "$output_dir" 2>/dev/null) || error "Invalid output directory path."

    info "Fetching latest release information from GitHub..."

    # Download the release information with retry.
    local release_info
    release_info=$(download_with_retry "$GITHUB_API_URL" 3) || true

    if [[ -z "$release_info" ]]; then
        error "Failed to fetch release information from GitHub."
    fi

    # Check for API rate limit or errors.
    if [[ "$release_info" == *'"message"'* ]]; then
        local message
        message=$(extract_json_value "$release_info" "message")

        if [[ "$message" == *"API rate limit exceeded"* ]] || [[ "$message" == *"rate limit"* ]]; then
            error "GitHub API rate limit exceeded. Set GITHUB_TOKEN (or GH_TOKEN) environment variable to increase limits (60 req/hr -> 5000 req/hr)."
        fi

        error "GitHub API error: $message"
    fi

    # Extract release information.
    local tag_name
    tag_name=$(extract_json_value "$release_info" "tag_name")

    if [[ -z "$tag_name" ]]; then
        error "Could not determine the latest release version."
    fi

    info "Latest release: $tag_name"

    # Create output directory if it does not exist.
    mkdir -p "$output_dir"
    info "Using output directory: $output_dir"

    # Set up cleanup trap for partial downloads.
    trap cleanup ERR EXIT INT TERM

    # Extract asset URLs.
    local asset_urls
    asset_urls=$(extract_asset_urls "$release_info")

    if [[ -z "$asset_urls" ]]; then
        error "No release assets found for $tag_name."
    fi

    # Download all release assets.
    info "Downloading release assets..."

    local download_failed=0
    local url filename filepath
    while IFS= read -r url; do
        if [[ -n "$url" ]]; then
            # Validate URL is from expected GitHub releases domain.
            local expected_prefix="https://github.com/${GITHUB_REPO}/releases/download/"
            if [[ "$url" != "${expected_prefix}"* ]]; then
                warn "Skipping URL from unexpected domain: $url"
                continue
            fi

            # Sanitize filename.
            filename=$(basename -- "$url" | tr -cd '[:alnum:]._-')

            if [[ -z "$filename" ]]; then
                warn "Could not determine filename for: $url"
                download_failed=1
                continue
            fi

            filepath="${output_dir}/${filename}"

            # Check if file already exists.
            if [[ -f "$filepath" ]] && [[ "$force_download" != "true" ]]; then
                info "File already exists, skipping: $filename (use --force to re-download)"
                continue
            fi

            CURRENT_DOWNLOAD="$filepath"

            info "Downloading: $filename"
            download_to_file "$url" "$filepath"

            if [[ -f "$filepath" ]] && [[ -s "$filepath" ]]; then
                info "Downloaded: $filepath"
                CURRENT_DOWNLOAD=""
            else
                warn "Failed to download $filename"
                CURRENT_DOWNLOAD=""
                download_failed=1
            fi
        fi
    done <<< "$asset_urls"

    if (( download_failed == 1 )); then
        error "One or more downloads failed."
    fi

    info "Download complete."
    info "Files saved to: $output_dir"

    # Print quick-start hint.
    echo ""
    info "Quick start:"
    info "  cd $output_dir"
    info "  tar -xzf microvm-standalone-256mb.tar.gz"
    info "  cd microvm-standalone-256mb"
    info "  echo \"print('Hello from Nanvix!')\" > mnt/bootstrap.py"
    info "  ./bin/nanvixd.elf -ramfs nanvix_rootfs.img -mount ./mnt -- python3.initrd"
}

# Run main function.
main "$@"
