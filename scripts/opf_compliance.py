# standard modules
import copy
import logging
import os
import traceback
# 3rd party modules
from configobj import ConfigObj
# PFP modules
from scripts import pfp_utils
from scripts import pfp_compliance

logger = logging.getLogger("pfp_log")

def ParsePPControlFile(cf):
    """
    Purpose:
     Check the contents of the P1 control file.
     If the P1 control file contents are OK, return with the required information.
     If the P1 control file contents are not OK, return with an error message.
    """
    logger.info(" Parsing the P1 control file")
    # create the settings dictionary
    f1_info = {"status": {"value": 0, "message": "OK"},
              "read_excel": {}, "Corrections": {}}
    f1ire = f1_info["read_excel"]
    # copy the files section from the control file
    f1ire["Files"] = copy.deepcopy(cf["Files"])
    f1ire["Files"]["file_name"] = os.path.join(cf["Files"]["file_path"], cf["Files"]["in_filename"])
    f1ire["Files"]["in_headerrow"] = cf["Files"]["in_headerrow"]
    f1ire["Files"]["in_firstdatarow"] = cf["Files"]["in_firstdatarow"]
    # get the global attributes
    f1ire["Global"] = copy.deepcopy(cf["Global"])
    # get the variables
    f1ire["Variables"] = copy.deepcopy(cf["Variables"])
    return f1_info
def check_pp_controlfile(cfg):
    """
    Purpose:
     Check the PP control file to make sure it contains all information
     needed to run PP and that all information is correct.
    Usage:
    Side effects:
     If output path folder exists, creates folders for each correction standard name 
    Author: PHHC
    Date: October 2023
    """
    try:
        ok = True
        cfg_labels = sorted(list(cfg["Variables"].keys()))
        base_path = pfp_utils.get_base_path()
        std_name = os.path.join(base_path, "controlfiles", "standard", "check_pp_controlfile.txt")
        std = ConfigObj(std_name, indent_type="    ", list_values=False, write_empty_values=True)
        std_labels = sorted(list(std["Variables"].keys()))
        # initialise the messages dictionary
        messages = {"ERROR":[], "WARNING": [], "INFO": []}
        # check the files section
        pp_check_files(cfg, std, messages)
        # check the global attributes section
        px_check_global_attributes(cfg, std, messages)
        # check variables whose name exactly matches an entry in the settings/l1.txt control file
        done = []
        label_matches = [l for l in cfg_labels if l in std_labels]
        for cfg_label in label_matches:
            std_label = cfg_label
            # check variable 'Attr' section
            pfp_compliance.l1_check_variables_sections(cfg, std, cfg_label, std_label, messages)
            # append this variable name to the done list
            done.append(cfg_label)
        # check variables where the first characters of the name match an entry in settings/l1.txt
        cfg_labels = sorted(list(cfg["Variables"].keys()))
        for std_label in std_labels:
            lsl = len(std_label)
            label_matches = [l for l in cfg_labels if l[:min([len(l),lsl])] == std_label and l not in done]
            for cfg_label in label_matches:
                # check variable 'Attr' section
                pfp_compliance.l1_check_variables_sections(cfg, std, cfg_label, std_label, messages)
                # append this variable name to the done list
                done.append(cfg_label)
        # check for duplicate netCDF variable labels
        pfp_compliance.l1_check_nc_labels(cfg, messages)
        # check for duplicate input variable labels
        pfp_compliance.l1_check_input_labels(cfg, messages)
        # check IRGA and sonic instrument type
        pfp_compliance.l1_check_irga_sonic_type(cfg, messages)
        if len(messages["ERROR"]) > 0:
            ok = False
    except Exception:
        ok = False
        error_message = " Error checking PP control file, see below for details ... "
        logger.error(error_message)
        error_message = traceback.format_exc()
        logger.error(error_message)
    return ok
def check_px_controlfile(cfg):
    """
    Purpose:
     Check the PP's correction control file to make sure it contains all information
     needed to run PP and that all information is correct.
    Usage:
    Side effects:
     If output path folder exists, creates folders for each correction standard name 
    Author: PHHC
    Date: October 2023
    """
    try:
        ok = True
        cfg_labels = sorted(list(cfg["Variables"].keys()))
        base_path = pfp_utils.get_base_path()
        std_name = os.path.join(base_path, "controlfiles", "standard", "check_pp_controlfile.txt")
        std = ConfigObj(std_name, indent_type="    ", list_values=False, write_empty_values=True)
        std_labels = sorted(list(std["Variables"].keys()))
        # initialise the messages dictionary
        messages = {"ERROR":[], "WARNING": [], "INFO": []}
        # check the files section
        px_check_files(cfg, std, messages)
        if len(messages["ERROR"]) > 0:
            ok = False
    except Exception:
        ok = False
        error_message = " Error checking PP control file, see below for details ... "
        logger.error(error_message)
        error_message = traceback.format_exc()
        logger.error(error_message)
    return ok
def px_check_global_attributes(cfg, std, messages):
    # check the 'Global' section exists
    if "Global" in cfg:
        # check the required global attributes exist
        px_check_global_required(cfg, std, messages)
        # check the forced global attributes
        pfp_compliance.l1_check_global_forced(cfg, std, messages)
        # check the recommended global attributes
        pfp_compliance.l1_check_global_recommended(cfg, std, messages)
    return
def px_check_global_required(cfg, std, messages):
    # check the global attributes
    required = std["Global"]["Required"]
    cfg_global = sorted(list(cfg["Global"].keys()))
    # check the required global attributes are present
    for item in required:
        if item not in cfg_global:
            msg = "Global: " + item + " not in section (required)"
            messages["ERROR"].append(msg)
    # check time step is present and makes sense
    if "time_step" in cfg["Global"]:
        try:
            ts = int(cfg["Global"]["time_step"])
        except ValueError:
            msg = "Global: 'time_step' is not a number"
            messages["ERROR"].append(msg)
        if ts not in [20, 10, 0.05, 0.1]:
            msg = "Global : 'time_step' must be 20, 10, 0.05 or 0.1"
            messages["ERROR"].append(msg)
    # check latitude is present and makes sense
    if "latitude" in cfg["Global"]:
        try:
            lat = float(cfg["Global"]["latitude"])
            if lat < -90.0 or lat > 90.0:
                msg = "Global: 'latitude' must be between -90 and 90"
                messages["ERROR"].append(msg)
        except ValueError:
            msg = "Global: 'latitude' is not a number"
            messages["ERROR"].append(msg)
    # check longitude is present and makes sense
    if "longitude" in cfg["Global"]:
        try:
            lon = float(cfg["Global"]["longitude"])
            if lon < -180.0 or lat > 180.0:
                msg = "Global: 'longitude' must be between -180 and 180"
                messages["ERROR"].append(msg)
        except ValueError:
            msg = "Global: 'longitude' is not a number"
            messages["ERROR"].append(msg)
    return
def px_check_files(cfg, std, messages):
    # check the Files section exists
    if ("Files" in cfg):
        # check the output file type
        if ("out_filename" in cfg["Files"] and "out_filepath" in cfg["Files"]):
            out_filepath = os.path.join(cfg["Files"]["out_filepath"],
                                        cfg["Files"]["out_filename"])
            out_filepath = os.path.dirname(out_filepath)
            # check out_filepath directory exists
            if os.path.isdir(out_filepath):
                pass
            else:
                msg = "Files: " + out_filepath + " doesn't exist, creating ..."
                messages["INFO"].append(msg)
                os.mkdir(out_filepath)
        else:
            msg = "Files: 'out_filename' not in section"
            messages["ERROR"].append(msg)
    return 
def pp_check_files(cfg, std, messages):
    # check the Files section exists
    if ("Files" in cfg):
        # check file_path is in the Files section
        if "file_path" in cfg["Files"]:
            file_path = cfg["Files"]["file_path"]
            # check file_path directory exists
            if os.path.isdir(file_path):
                pass
            else:
                msg = "Files: " + file_path + " is not a directory"
                messages["ERROR"].append(msg)
        else:
            msg = "Files: 'file_path' not in section"
            messages["ERROR"].append(msg)
        # check in_filename is in the Files section
        if "in_filename" in cfg["Files"]:
            file_names = cfg["Files"]["in_filename"]
            file_names = file_names.split(",")
            for file_name in file_names:
                file_parts = os.path.splitext(file_name)
                # check the file type is supported
                if (file_parts[-1].lower() in  [".xls", ".xlsx", ".csv"]):
                    file_uri = os.path.join(file_path, file_name)
                    if os.path.isfile(file_uri):
                        pass
                    else:
                        msg = "Files: " + file_name + " not found"
                        messages["ERROR"].append(msg)
                else:
                    msg = "Files: " + file_name + " doesn't end with .xls, .xlsx or .csv"
                    messages["ERROR"].append(msg)
        else:
            msg = "Files: 'in_filename' not in section"
            messages["ERROR"].append(msg)
        # check in_firstdatarow is in the Files section
        if "in_firstdatarow" in cfg["Files"]:
            for item in cfg["Files"]["in_firstdatarow"].split(","):
                # check to see if in_firdtdatarow is an integer
                try:
                    i = int(item)
                except:
                    msg = "Files: 'in_firstdatarow' is not an integer"
                    messages["ERROR"].append(msg)
        # check in_headerrow is in the Files section
        if "in_headerrow" in cfg["Files"]:
            for item in cfg["Files"]["in_headerrow"].split(","):
                # check to see if in_heafderrow is an integer
                try:
                    i = int(item)
                except:
                    msg = "Files: 'in_headerrow' is not an integer"
                    messages["ERROR"].append(msg)
        # check out_filepath is in the Files section
        if "out_filepath" in cfg["Files"]:
            out_filepath = cfg["Files"]["out_filepath"]
            # check out_filepath directory exists
            if os.path.isdir(out_filepath):
                pass
            else:
                msg = "Files: " + out_filepath + " doesn't exist, creating ..."
                messages["INFO"].append(msg)
                os.mkdir(out_filepath)
        else:
            cfg["Files"]["out_filepath"] = cfg["Files"]["file_path"]
            msg = "Files: 'out_filepath' not in section, using file_path as output folder"
            messages["ERROR"].append(msg)
        # check the output file type
        if "out_filename" in cfg["Files"]:
            file_name = cfg["Files"]["out_filename"]
            file_parts = os.path.splitext(file_name)
            if (file_parts[-1].lower() in [".nc"]):
                pass
            else:
                msg = "Files: " + file_name + " doesn't end with .nc"
                messages["ERROR"].append(msg)
        else:
            msg = "Files: 'out_filename' not in section"
            messages["ERROR"].append(msg)
    else:
        msg = "'Files' section not in control file"
        messages["ERROR"].append(msg)
    return