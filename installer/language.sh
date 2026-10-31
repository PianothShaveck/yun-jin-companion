# Installer messages default to English; choose the app language in its first-run window.
: "${YUNJIN_LANGUAGE:=en}"
export YUNJIN_LANGUAGE
yj_text() {
    case "$YUNJIN_LANGUAGE" in it) printf '%s\n' "$1";; zh-CN) printf '%s\n' "$3";; *) printf '%s\n' "$2";; esac
}
