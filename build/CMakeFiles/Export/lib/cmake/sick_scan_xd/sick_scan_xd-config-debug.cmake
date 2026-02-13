#----------------------------------------------------------------
# Generated CMake target import file for configuration "Debug".
#----------------------------------------------------------------

# Commands may need to know the format version.
set(CMAKE_IMPORT_FILE_VERSION 1)

# Import target "sick_scan_xd::sick_scan_xd_shared_lib" for configuration "Debug"
set_property(TARGET sick_scan_xd::sick_scan_xd_shared_lib APPEND PROPERTY IMPORTED_CONFIGURATIONS DEBUG)
set_target_properties(sick_scan_xd::sick_scan_xd_shared_lib PROPERTIES
  IMPORTED_LOCATION_DEBUG "${_IMPORT_PREFIX}/lib/libsick_scan_xd_shared_lib.so"
  IMPORTED_SONAME_DEBUG "libsick_scan_xd_shared_lib.so"
  )

list(APPEND _IMPORT_CHECK_TARGETS sick_scan_xd::sick_scan_xd_shared_lib )
list(APPEND _IMPORT_CHECK_FILES_FOR_sick_scan_xd::sick_scan_xd_shared_lib "${_IMPORT_PREFIX}/lib/libsick_scan_xd_shared_lib.so" )

# Commands beyond this point should not need to know the version.
set(CMAKE_IMPORT_FILE_VERSION)
