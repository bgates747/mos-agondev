#include <agon/mos.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#define TARGET_GOLDEN_PATTERN(pattern) ((void)sizeof(pattern))
#define EXTRACT_FLAG_AUTO_TERMINATE 0x01
#define GSTRANS_FLAG_NO_TRACE 0x80
#define RESOLVE_OMIT_EXPAND 0x40

static unsigned int failures;
static char debug[128];
static FIL sparse_file;
static const char persistent_payload[] = "PORT-201-PERSIST\r\n";

static void emit(const char *text) {
    while (*text != '\0') {
        putch((unsigned char)*text++);
    }
}

static void check(int condition, const char *name) {
    if (!condition) {
        emit("CONTRACT-FAIL ");
        emit(name);
        emit("\r\n");
        ++failures;
    }
}

static void check_formatter(void) {
    char buffer[96];

    TARGET_GOLDEN_PATTERN("%*lu");
    check(sprintf(buffer, "%*lu", 10, 4294967295UL) == 10 &&
              strcmp(buffer, "4294967295") == 0,
          "format-u32-width");
    check(sprintf(buffer, "%*lu", 1, 0UL) == 1 &&
              strcmp(buffer, "0") == 0,
          "format-u32-min");
    TARGET_GOLDEN_PATTERN("%u");
    check(sprintf(buffer, "%u", 16777215U) == 8 &&
              strcmp(buffer, "16777215") == 0,
          "format-u24-max");
    TARGET_GOLDEN_PATTERN("%d");
    check(sprintf(buffer, "%d", (-8388607 - 1)) == 8 &&
              strcmp(buffer, "-8388608") == 0,
          "format-s24-min");
    TARGET_GOLDEN_PATTERN("%06x");
    check(sprintf(buffer, "%06x", 0xabcU) == 6 &&
              strcmp(buffer, "000abc") == 0,
          "format-hex-padding");
    TARGET_GOLDEN_PATTERN("%02X");
    check(sprintf(buffer, "%02X", 0xAU) == 2 &&
              strcmp(buffer, "0A") == 0,
          "format-upper-hex");
    TARGET_GOLDEN_PATTERN("%-*s");
    check(sprintf(buffer, "%-*s", 5, "xy") == 5 &&
              strcmp(buffer, "xy   ") == 0,
          "format-left-width");
    TARGET_GOLDEN_PATTERN("%.*s");
    check(sprintf(buffer, "%.*s", 3, "abcdef") == 3 &&
              strcmp(buffer, "abc") == 0,
          "format-precision");
    TARGET_GOLDEN_PATTERN("%c");
    TARGET_GOLDEN_PATTERN("%%");
    TARGET_GOLDEN_PATTERN("%s");
    check(sprintf(buffer, "%c %% %s", 'Z', "ok") == 6 &&
              strcmp(buffer, "Z % ok") == 0,
          "format-char-percent-string");
    TARGET_GOLDEN_PATTERN("%02d");
    check(sprintf(buffer, "%02d", 7) == 2 && strcmp(buffer, "07") == 0,
          "format-s24-width-2-zero");
    TARGET_GOLDEN_PATTERN("%04d");
    check(sprintf(buffer, "%04d", -7) == 4 && strcmp(buffer, "-007") == 0,
          "format-s24-width-4-zero");
    TARGET_GOLDEN_PATTERN("%06X");
    check(sprintf(buffer, "%06X", 0xffffffU) == 6 &&
              strcmp(buffer, "FFFFFF") == 0,
          "format-u24-upper-width-6-zero");
    TARGET_GOLDEN_PATTERN("%2d");
    check(sprintf(buffer, "%2d", -8) == 2 && strcmp(buffer, "-8") == 0,
          "format-s24-width-2");
    TARGET_GOLDEN_PATTERN("%4d");
    check(sprintf(buffer, "%4d", 7) == 4 && strcmp(buffer, "   7") == 0,
          "format-s24-width-4");
    TARGET_GOLDEN_PATTERN("%6d");
    check(sprintf(buffer, "%6d", (-8388607 - 1)) == 8 &&
              strcmp(buffer, "-8388608") == 0,
          "format-s24-width-6-overflow");
    check(printf("FORMAT-PRINTF\n\r") == 15, "format-printf-raw-newline");
}

static void check_string_api(void) {
    char extracted_source[] = "  \"alpha beta\" tail";
    char *extracted = NULL;
    char *extracted_next = NULL;
    char gs_source[] = "A||B";
    char *transinfo = NULL;
    char gs_result[8] = {0};
    unsigned int gs_length = 0;
    char gs_character = 0;
    uint8_t gs_status;
    char substitution_template[] = "A%0B%1";
    char substitution_arguments[] = "aa bb cc";
    char substitution[16] = {0};
    int substitution_length;

    check(mos_extractstring(&extracted, &extracted_next, extracted_source,
                            NULL, EXTRACT_FLAG_AUTO_TERMINATE) == FR_OK &&
              extracted == extracted_source + 3 &&
              strcmp(extracted, "alpha beta") == 0 &&
              extracted_next == extracted_source + 14 &&
              strcmp(extracted_next, " tail") == 0,
          "api-extractstring-pointer-outputs");

    gs_status = mos_gsinit(gs_source, &transinfo, GSTRANS_FLAG_NO_TRACE);
    while (gs_status == FR_OK && transinfo != NULL &&
           gs_length + 1 < sizeof(gs_result)) {
        gs_status = mos_gsread(&gs_character, &transinfo);
        if (gs_status == FR_OK && gs_character != '\0') {
            gs_result[gs_length++] = gs_character;
        }
    }
    check(gs_status == FR_OK && transinfo == NULL &&
              strcmp(gs_result, "A|B") == 0,
          "api-gsinit-gsread-pointer-state");

    substitution_length = mos_substituteargs(
        substitution_template, substitution_arguments, substitution,
        0x010000, 1);
    check(substitution_length == 7 && strcmp(substitution, "AaaBbb") == 0,
          "api-substituteargs-u24-length");
}

static __attribute__((noinline)) void check_number_api(void) {
    char numeric[] = "12345";
    char *number_end = NULL;
    uint24_t number = 0;
    int status =
        mos_extractnumber(&number, &number_end, numeric, NULL, 0);

    check(status == FR_OK && number == 12345U && number_end == numeric + 5,
          "api-extractnumber-u24-output");
}

static void check_directory_api(void) {
    DIR directory_handle = {0};
    FILINFO file_info = {0};
    uint8_t status;
    unsigned int entries = 0;
    int saw_nested = 0;
    int saw_seek = 0;
    char cwd[32] = {0};
    char volume_label[24] = {0};
    uint32_t volume_serial = 0xa5a5a5a5UL;

    status = ffs_stat(&file_info, "/seek.txt");
    check(status == FR_OK && file_info.fsize == 10 &&
              strcmp(file_info.fname, "seek.txt") == 0 &&
              (file_info.fattrib & AM_DIR) == 0,
          "api-ffs-stat-file");
    memset(&file_info, 0, sizeof(file_info));
    check(ffs_stat(&file_info, "/nested") == FR_OK &&
              strcmp(file_info.fname, "nested") == 0 &&
              (file_info.fattrib & AM_DIR) != 0,
          "api-ffs-stat-directory");
    check((uint24_t)ffs_stat(&file_info, "/missing-stat-entry") == FR_NO_FILE,
          "api-ffs-stat-u8-zero-extension");

    status = ffs_dopen(&directory_handle, "/");
    check(status == FR_OK, "api-ffs-dopen");
    if (status == FR_OK) {
        do {
            memset(&file_info, 0, sizeof(file_info));
            status = ffs_dread(&directory_handle, &file_info);
            if (status != FR_OK || file_info.fname[0] == '\0') {
                break;
            }
            saw_nested |= strcmp(file_info.fname, "nested") == 0 &&
                          (file_info.fattrib & AM_DIR) != 0;
            saw_seek |= strcmp(file_info.fname, "seek.txt") == 0 &&
                        file_info.fsize == 10;
            ++entries;
        } while (entries < 16);
        check(status == FR_OK && entries < 16 && saw_nested && saw_seek,
              "api-ffs-dread-enumeration");
        check(ffs_dclose(&directory_handle) == FR_OK, "api-ffs-dclose");
    }

    memset(&directory_handle, 0, sizeof(directory_handle));
    memset(&file_info, 0, sizeof(file_info));
    status = ffs_dfindfirst(&directory_handle, &file_info, "/nested",
                            "alpha.*");
    check(status == FR_OK && strcmp(file_info.fname, "alpha.txt") == 0 &&
              file_info.fsize == 11,
          "api-ffs-dfindfirst");
    if (status == FR_OK) {
        status = ffs_dfindnext(&directory_handle, &file_info);
        check(status == FR_OK && file_info.fname[0] == '\0',
              "api-ffs-dfindnext-end");
        check(ffs_dclose(&directory_handle) == FR_OK,
              "api-ffs-dfind-close");
    }

    check(ffs_getcwd(cwd, sizeof(cwd)) == FR_OK && strcmp(cwd, "/") == 0,
          "api-ffs-getcwd");
    check(ffs_getlabel("", volume_label, &volume_serial) == FR_OK &&
              strcmp(volume_label, "hostfs") == 0,
          "api-ffs-getlabel");
}

static void check_read_api(void) {
    FIL file = {0};
    FIL *handle_file = NULL;
    char read_buffer[32];
    uint24_t count;
    uint8_t handle;

    handle = mos_fopen("lines.txt", FA_READ);
    check(handle != 0, "api-mos-fopen-read");
    if (handle != 0) {
        memset(read_buffer, 0, sizeof(read_buffer));
        count = mos_fread(handle, read_buffer, 19);
        handle_file = mos_getfil(handle);
        check(count == 18 && strcmp(read_buffer, "line-one\nline-two\n") == 0,
              "api-mos-fread-u24-return");
        check(handle_file != NULL && handle_file->fptr == 18,
              "api-mos-getfil-pointer");
        check(mos_feof(handle) == 1, "api-mos-feof");
        mos_fclose(handle);
    }

    uint8_t status = ffs_fopen(&file, "/lines.txt", FA_READ);
    check(status == FR_OK, "api-ffs-open-read");
    if (status == FR_OK) {
        memset(read_buffer, 0, sizeof(read_buffer));
        count = ffs_fread(&file, read_buffer, 19);
        check(count == 18 && strcmp(read_buffer, "line-one\nline-two\n") == 0,
              "api-ffs-fread-u24-return");
        check(ffs_ferror(&file) == FR_OK, "api-ffs-ferror");
        check(ffs_feof(&file) == 1, "api-ffs-feof-wide");
        check(ffs_fclose(&file) == FR_OK, "api-ffs-close-wide");
    }
}

static void check_fatfs_api(void) {
    uint32_t file_size = 0;
    uint32_t position = 0;
    char final_byte = 0;
    uint8_t status = ffs_fopen(&sparse_file, "/abi-sparse.bin", FA_READ);
    char line[32] = {0};
    uint32_t pointer_offset = 4;

    check(status == FR_OK, "api-ffs-open-readonly");
    if (status != FR_OK) {
        return;
    }
    check(ffs_flseek(&sparse_file, 0x01020304UL) == FR_OK,
          "api-ffs-seek-u32");
    check(ffs_ftell(&sparse_file, &position) == FR_OK &&
              position == 0x01020304UL,
          "api-ffs-tell-u32");
    check(ffs_fread(&sparse_file, &final_byte, 1) == 1 && final_byte == 'Q',
          "api-ffs-read-final-byte");
    check(ffs_ftell(&sparse_file, &position) == FR_OK &&
              position == 0x01020305UL,
          "api-ffs-tell-eof-u32");
    check(ffs_fclose(&sparse_file) == FR_OK, "api-ffs-close");

    status = ffs_fopen(&sparse_file, "/seek.txt", FA_READ);
    check(status == FR_OK, "api-ffs-open-small-readonly");
    if (status != FR_OK) {
        return;
    }
    file_size = 0xa5a5a5a5UL;
    check(ffs_fsize(&sparse_file, &file_size) == FR_OK && file_size == 10,
          "api-ffs-size-output-u32");
    check(ffs_flseek_p(&sparse_file, &pointer_offset) == FR_OK &&
              ffs_ftell(&sparse_file, &position) == FR_OK && position == 4,
          "api-ffs-flseek-p-pointer-u32");
    check(ffs_flseek(&sparse_file, 10) == FR_OK, "api-ffs-seek-small-eof");
    check(ffs_feof(&sparse_file) == 1, "api-ffs-eof");
    check(ffs_fclose(&sparse_file) == FR_OK, "api-ffs-close-small");

    status = ffs_fopen(&sparse_file, "/lines.txt", FA_READ);
    check(status == FR_OK, "api-ffs-open-lines-readonly");
    if (status == FR_OK) {
        check(ffs_fgets(&sparse_file, line, sizeof(line)) ==
                      (uint8_t *)line &&
                  strcmp(line, "line-one\n") == 0,
              "api-ffs-fgets-pointer-return");
        check(ffs_ferror(&sparse_file) == FR_OK, "api-ffs-ferror-lines");
        check(ffs_fclose(&sparse_file) == FR_OK, "api-ffs-close-lines");
    }
}

static void check_write_api(void) {
    FIL file = {0};
    FILINFO info = {0};
    char buffer[sizeof(persistent_payload)] = {0};
    char mos_buffer[8] = {0};
    uint8_t handle = mos_fopen("/mos-write.tmp", FA_CREATE_ALWAYS | FA_WRITE);
    uint8_t status;
    char save_source[] = "SAVE-BYTES";
    char save_result[sizeof(save_source)] = {0};

    check(handle != 0, "api-mos-fopen-write");
    if (handle != 0) {
        check(mos_fwrite(handle, "MOS", 3) == 3,
              "api-mos-fwrite-u24-return");
        mos_fputc(handle, '!');
        mos_fclose(handle);
    }
    handle = mos_fopen("/mos-write.tmp", FA_READ);
    check(handle != 0, "api-mos-reopen-write-result");
    if (handle != 0) {
        check(mos_fread(handle, mos_buffer, sizeof(mos_buffer)) == 4 &&
                  memcmp(mos_buffer, "MOS!", 4) == 0,
              "api-mos-write-readback");
        mos_fclose(handle);
    }
    check(ffs_unlink("/mos-write.tmp") == FR_OK, "api-mos-write-cleanup");

    check(mos_save("/mos-save.bin", save_source, sizeof(save_source)) == FR_OK,
          "api-mos-save");
    check(mos_load("/mos-save.bin", save_result, sizeof(save_result)) == FR_OK &&
              memcmp(save_result, save_source, sizeof(save_source)) == 0,
          "api-mos-load");
    check(mos_copy("/mos-save.bin", "/mos-copy.bin") == FR_OK,
          "api-mos-copy");
    check(mos_ren("/mos-copy.bin", "/mos-renamed.bin") == FR_OK,
          "api-mos-ren");
    check(mos_del("/mos-save.bin") == FR_OK, "api-mos-del-source");
    check(mos_del("/mos-renamed.bin") == FR_OK, "api-mos-del-renamed");

    memset(&file, 0, sizeof(file));
    status = ffs_fopen(&file, "/ffs-put.tmp", FA_CREATE_ALWAYS | FA_WRITE);
    check(status == FR_OK, "api-ffs-open-put");
    if (status == FR_OK) {
        /* Fab traps f_putc below MOS and leaves BC unchanged, so only the
         * resulting byte is portable candidate/reference evidence here. */
        (void)ffs_fputc(&file, 'A');
        check(ffs_fputs(&file, "BC") == 2, "api-ffs-fputs");
        check(ffs_fclose(&file) == FR_OK, "api-ffs-close-put");
    }
    memset(&file, 0, sizeof(file));
    memset(buffer, 0, sizeof(buffer));
    status = ffs_fopen(&file, "/ffs-put.tmp", FA_READ);
    check(status == FR_OK && ffs_fread(&file, buffer, sizeof(buffer)) == 3 &&
              memcmp(buffer, "ABC", 3) == 0,
          "api-ffs-put-readback");
    if (status == FR_OK) {
        check(ffs_fclose(&file) == FR_OK, "api-ffs-close-put-readback");
    }
    check(ffs_unlink("/ffs-put.tmp") == FR_OK, "api-ffs-put-cleanup");

    status = ffs_stat(&info, "/abi-write-dir/persisted.bin");

    if (status == FR_NO_FILE || status == FR_NO_PATH) {
        check(ffs_mkdir("/abi-write-dir") == FR_OK, "api-ffs-mkdir");
        check(ffs_chdir("/abi-write-dir") == FR_OK, "api-ffs-chdir-created");
        status = ffs_fopen(&file, "stage.tmp", FA_CREATE_ALWAYS | FA_WRITE);
        check(status == FR_OK, "api-ffs-open-write");
        if (status == FR_OK) {
            check(ffs_fwrite(&file, persistent_payload,
                             sizeof(persistent_payload) - 1) ==
                      sizeof(persistent_payload) - 1,
                  "api-ffs-fwrite-u24-return");
            check(ffs_fclose(&file) == FR_OK, "api-ffs-close-write");
        }
        check(ffs_rename("stage.tmp", "persisted.bin") == FR_OK,
              "api-ffs-rename");
        check(ffs_chdir("/") == FR_OK, "api-ffs-chdir-root");
        emit("WRITE-PHASE-CREATE\r\n");
    } else {
        check(status == FR_OK && info.fsize == sizeof(persistent_payload) - 1,
              "api-ffs-persisted-stat");
        status = ffs_fopen(&file, "/abi-write-dir/persisted.bin", FA_READ);
        check(status == FR_OK, "api-ffs-open-persisted");
        if (status == FR_OK) {
            check(ffs_fread(&file, buffer, sizeof(persistent_payload) - 1) ==
                          sizeof(persistent_payload) - 1 &&
                      memcmp(buffer, persistent_payload,
                             sizeof(persistent_payload) - 1) == 0,
                  "api-ffs-cold-boot-persistence");
            check(ffs_fclose(&file) == FR_OK, "api-ffs-close-persisted");
        }
        check(ffs_unlink("/abi-write-dir/persisted.bin") == FR_OK,
              "api-ffs-unlink-persisted");
        check(ffs_unlink("/abi-write-dir") == FR_OK,
              "api-ffs-unlink-directory");
        emit("WRITE-PHASE-VERIFY\r\n");
    }
}

static void check_mos_api(void) {
    char arguments[] = "zero one two";
    char *argument = NULL;
    char *argument_end = NULL;
    char escape_source[] = {'A', '|', 1, '\0'};
    char escaped[16] = {0};
    uint24_t escaped_length = sizeof(escaped);
    char error[48] = {0};
    char rtc[48] = {0};
    char absolute_input[] = "bin";
    char absolute[48] = {0};
    int absolute_length = sizeof(absolute);
    char directory[48] = {0};
    int directory_length = sizeof(directory);
    uint32_t clock_before;
    uint32_t clock_after;
    char gstrans_source[] = "abc";
    char gstrans_result[8] = {0};
    int gstrans_read = -1;
    uint8_t seek_handle;
    int seek_status;
    char seek_character;
    char resolve_input[] = "/nested/alpha.txt";
    char resolved[64] = {0};
    int resolved_length = sizeof(resolved);
    uint8_t resolved_index = 0;
    DIR resolved_directory = {0};

    int pmatch_result = mos_pmatch("a", "b", 0);
    if (pmatch_result != 1) {
        sprintf(debug, "PMATCH=%d\r\n", pmatch_result);
        emit(debug);
    }
    check(pmatch_result == 1, "api-pmatch");
    check(mos_pmatch("b", "a", 0) == -1, "api-pmatch-signed-return");
    check(strcmp(mos_getleafname("/alpha/beta.txt"), "beta.txt") == 0,
          "api-leafname");

    mos_getargument(&argument, &argument_end, arguments, 1);
    check(argument == arguments + 5 && argument_end == arguments + 8,
          "api-getargument");
    argument = arguments;
    argument_end = arguments;
    mos_getargument(&argument, &argument_end, arguments, 0x010000U);
    check(argument == NULL && argument_end == NULL,
          "api-getargument-u24-high-byte");

    int escape_result = mos_escapestring(
        &escaped_length, escape_source, escaped, sizeof(escaped));
    if (escape_result != FR_OK || escaped_length != 6 ||
        memcmp(escaped, "A|||A", 5) != 0) {
        sprintf(debug, "ESCAPE=%d,%u,%02X%02X%02X%02X%02X\r\n",
                escape_result, escaped_length, (unsigned char)escaped[0],
                (unsigned char)escaped[1], (unsigned char)escaped[2],
                (unsigned char)escaped[3], (unsigned char)escaped[4]);
        emit(debug);
    }
    check(escape_result == FR_OK && escaped_length == 6 &&
              memcmp(escaped, "A|||A", 5) == 0,
          "api-escapestring");

    int gstrans_status = mos_gstrans(gstrans_source, gstrans_result, 0x010000,
                                    &gstrans_read, 0);
    if (gstrans_status != FR_OK || gstrans_read != 3 ||
        strcmp(gstrans_result, "abc") != 0) {
        sprintf(debug, "GSTRANS=%d,%d,<%s>\r\n", gstrans_status,
                gstrans_read, gstrans_result);
        emit(debug);
    }
    check(gstrans_status == FR_OK && gstrans_read == 3 &&
              strcmp(gstrans_result, "abc") == 0,
          "api-gstrans-u24-high-byte");

    mos_getError(FR_NO_FILE, error, sizeof(error));
    if (strcmp(error, "Could not find file") != 0) {
        sprintf(debug, "GETERROR=<%s>\r\n", error);
        emit(debug);
    }
    check(strcmp(error, "Could not find file") == 0, "api-geterror");

    int absolute_result =
        mos_getabsolutepath(absolute_input, absolute, &absolute_length);
    if (absolute_result != FR_OK || strcmp(absolute, "/bin") != 0) {
        sprintf(debug, "ABSOLUTE=%d,%d,<%s>\r\n", absolute_result,
                absolute_length, absolute);
        emit(debug);
    }
    check(absolute_result == FR_OK && strcmp(absolute, "/bin") == 0,
          "api-getabsolutepath");
    check(mos_getdirforpath("/bin/tool.bin", directory, &directory_length, 0) ==
                  FR_OK &&
              strcmp(directory, "/bin/") == 0,
          "api-getdirforpath");
    int is_missing = mos_isdirectory("/definitely-missing");
    if (is_missing != FR_NO_PATH) {
        sprintf(debug, "ISDIRECTORY=%d\r\n", is_missing);
        emit(debug);
    }
    check(is_missing == FR_NO_PATH, "api-isdirectory-missing");

    int rtc_length = mos_getrtc(rtc);
    if (rtc_length <= 0 || rtc[0] == '\0') {
        sprintf(debug, "GETRTC=%d,<%s>\r\n", rtc_length, rtc);
        emit(debug);
    }
    check(rtc_length > 0 && rtc[0] != '\0', "api-getrtc");
    clock_before = getsysvar_time();
    clock_after = getsysvar_time();
    check(clock_after >= clock_before, "api-u32-return");

    seek_handle = mos_fopen("seek.txt", FA_READ);
    seek_status = seek_handle ? mos_flseek_p(seek_handle, 3UL) : FR_INVALID_OBJECT;
    seek_character = seek_status == FR_OK ? mos_fgetc(seek_handle) : '\0';
    if (seek_handle) {
        mos_fclose(seek_handle);
    }
    if (!seek_handle || seek_status != FR_OK || seek_character != '3') {
        sprintf(debug, "FLSEEKP=%u,%d,%02X\r\n", seek_handle, seek_status,
                (unsigned char)seek_character);
        emit(debug);
    }
    check(seek_handle && seek_status == FR_OK && seek_character == '3',
          "api-flseek-p-u8-u32-slots");

    int resolve_status = mos_resolvepath(
        resolve_input, resolved, &resolved_length, &resolved_index,
        &resolved_directory, RESOLVE_OMIT_EXPAND);
    check(resolve_status == FR_OK &&
              strcmp(resolved, "/nested/alpha.txt") == 0 &&
              resolved_index == 1,
          "api-resolvepath-six-argument-dispatch");
    if (resolve_status == FR_OK) {
        check(ffs_dclose(&resolved_directory) == FR_OK,
              "api-resolvepath-directory-close");
    }
}

int main(void) {
    emit("CONTRACT-BEGIN\r\n");
    check_formatter();
    check_number_api();
    check_string_api();
    check_mos_api();
    check_directory_api();
    check_read_api();
    check_fatfs_api();
    check_write_api();
    if (failures == 0) {
        emit("CONTRACT-PASS\r\n");
        return 0;
    }
    emit("CONTRACT-FAILED\r\n");
    return 1;
}
