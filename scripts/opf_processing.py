# standard modules
import datetime
import logging
import re
import os
import copy
import traceback
# 3rd party modules
import numpy
import pandas
# PFP modules
from scripts import pfp_io
from scripts import pfp_utils
from scripts import pfp_ck
from scripts import pfp_ts
# new PFP modules
from scripts import opf_compliance
from scripts import opf_func_corrections

logger = logging.getLogger("pfp_log")


def do_retrieve_ds(cf_info, in_filepath):
    if not check_file_exits(in_filepath):
        ds1 = pfp_io.DataStructure()
        ds1.info["returncodes"]["value"] = 1
        ds1.info["returncodes"]["message"] = "An error occurred reading the input file"
        return ds1
    if os.path.split(in_filepath)[1] == ".nc":
        if not pfp_utils.file_exists(in_filepath):
            ds1 = pfp_io.DataStructure()
            ds1.info["returncodes"]["value"] = 1
            ds1.info["returncodes"]["message"] = "An error occurred reading the input file"
            return ds1
        ds1 = pfp_io.NetCDFRead(in_filepath)
    else:
        # read the input file into a pandas data frame
        dfs = pfp_io.ReadInputFile(cf_info)
        # discard empty data frames
        for key in list(dfs.keys()):
            if len(dfs[key]) == 0:
                dfs.pop(key)
        if len(list(dfs.keys())) == 0:
            ds1 = pfp_io.DataStructure()
            ds1.info["returncodes"]["value"] = 1
            ds1.info["returncodes"]["message"] = "An error occurred reading the input file"
            return ds1
        # merge the data frames (1 per Excel worksheet)
        df = pfp_io.MergeDataFrames(dfs, cf_info)
        # convert the data frame to a PFP data structure and add metadata
        ds1 = pfp_io.DataFrameToDataStructure(df, cf_info)
    return ds1


def do_corrections(main_ui, cf_level, ds):
    for i in list(cf_level["Corrections"].keys()):
        # check the stop flag
        if main_ui.stop_flag:
            # break out of the loop if user requested stop
            break
        cf_corr = copy.deepcopy(cf_level)
        # select only current correction
        cf_corr["Correction"] = cf_corr.pop("Corrections")[i]
        # aka
        long_name = cf_corr["Correction"]["Attr"]["long_name"]
        standard_name = cf_corr["Correction"]["Attr"]["standard_name"]
        level_folder = get_corrections_from_key_value("short_name", standard_name).get("short_name", "")
        level_folder = level_folder.get(standard_name, "level_unrecognized")
        descr_level = "description_" + standard_name
        # add correction name to output's folder name 
        cf_corr["Files"]["out_filename"] = os.path.join(level_folder, cf_corr["Files"]["out_filename"])
        # check the PP control file (for now not blocking anything)
        if opf_compliance.check_px_controlfile(cf_corr):
            logger.info("")
        else:
            msg = "Error occurred checking compliance of PP controlfile"
            logger.error(msg)
        # start applying correction
        msg = "Starting pre processing with " + long_name
        logger.info(msg)
        try:
            variables_requested = list(cf_corr["Correction"]["Variables"].keys())
            dataframe = convert_ds_to_dataframe(ds, subset=variables_requested, how="outer")
            if dataframe.empty:
                msg = f" Empty data for correction {func}. Check requested variables match existing ones."
                logger.error(msg)
                return 0
            # retrieve function
            function_name = cf_corr["Correction"]["Attr"]["func_name"].replace('"','').split("(")[0]
            func = getattr(opf_func_corrections, function_name)
            try:
                dataframe2 = func(dataframe, 
                                  *list(cf_corr["Correction"].get("args", {}).values()), 
                                  **cf_corr["Correction"].get("kwargs", {}))
            except Exception:
                msg = f" Error while running {func}"
                logger.error(msg)
                error_message = traceback.format_exc()
                logger.error(error_message)
                return 0
            if dataframe2.shape != dataframe.shape:
                msg = " Correction changed data dimensions from " + str(dataframe.shape) + " to " + str(dataframe2.shape)
                logger.warn(msg)
            # put back into datastructure
            for var_req in variables_requested:
                var = pfp_utils.GetVariable(ds, var_req)
                # save the non-corrected data
                var_before = copy.deepcopy(var)
                var_before["Label"] = var["Label"] + "b4" + level_folder
                pfp_utils.CreateVariable(ds, var_before)
                var_after = copy.deepcopy(var)
                var_after["Data"] = numpy.ma.array(dataframe2[var_req])
                # update the "description" attribute
                pfp_utils.append_to_attribute(var_after["Attr"], {descr_level:  long_name + " applied"})
                # and write the corrected data to the data structure
                pfp_utils.CreateVariable(ds, var_after)
        except Exception:
            msg = "Error occurred during pre processing with " + long_name
            logger.error(msg)
            error_message = traceback.format_exc()
            logger.error(error_message)
            return 0
        # save
        if cf_corr["Correction"]["Attr"].get("Saving", False):
            outfilename = pfp_io.get_outfilenamefromcf(cf_corr)
            pfp_io.NetCDFWrite(outfilename, ds)
    # save 
    outfilename = pfp_io.get_outfilenamefromcf(cf_corr)
    pfp_io.NetCDFWrite(outfilename, ds)
    return 1


def do_run_preprocess(main_ui):
    """
    Purpose:
     Reads raw input files, either an Excel workbook or a collection of CSV files,
     and returns the data as a data structure.
    Usage:
    Side effects:
     Returns a data structure containing the data specified in the P1
     control file.
    Author: PHHC
    Date: August 2023
    """
    if main_ui.mode == "interactive":
        tab_index_running = main_ui.tabs.tab_index_running
        cf_batch = main_ui.tabs.tab_dict[tab_index_running].get_data_from_model()
    elif main_ui.mode == "batch":
        cf_batch = main_ui.cfg
    else:
        msg = "Unrecognised option for mode (" + main_ui.mode + ")"
        logger.error(msg)
        raise RuntimeError
    start = datetime.datetime.now()
    msg = "Started pre processing at " + start.strftime("%Y%m%d%H%M")
    logger.info(msg)    
    # get filenames
    if ("$timestamp$" in cf_batch["Files"]["in_filename"]):
        file_pattern = cf_batch["Files"]["in_filename"].replace("$timestamp$", "(.+)")
        file_namesd = {}
        for root, directories, files in os.walk(cf_batch["Files"]["file_path"]):
            for name in files:
                dateparts = re.findall(file_pattern, name, flags=re.IGNORECASE)
                if len(dateparts) == 1:
                    file_namesd[dateparts[0]] = os.path.join(os.path.relpath(root,cf_batch["Files"]["file_path"]).replace(".", ""), name)
        file_names = list(file_namesd.values())
    else:
        file_names = pfp_utils.string_to_list(cf_batch["Files"]["in_filename"])
        date_pattern = cf_batch["Files"]["in_dateformat"]
        file_namesd = {n: re.findall(convert_dataformat_to_regex(date_pattern), n, flags=re.IGNORECASE) for n in file_names}
        file_namesd = {v[0]: n for n, v in file_namesd.items() if v}
    
    if not file_namesd:
        msg = "No input file was found using pattern " + cf_batch["Files"]["in_filename"] + " in " + cf_batch["Files"]["file_path"]
        logger.error(msg)    
    for timestamp, file_name in file_namesd.items():
        # check the stop flag
        if main_ui.stop_flag:
            main_ui
            # break out of the loop if user requested stop
            break
        # new file-specific cfg
        cf_file = copy.deepcopy(cf_batch)
        cf_file["Files"]["in_filename"] = file_name.replace("$timestamp$", timestamp)
        cf_file["Files"]["out_filename"] = cf_file["Files"]["out_filename"].replace("$timestamp$", timestamp)
        # parse the PP control file
        pp_info = opf_compliance.ParsePPControlFile(cf_file)
        msg = "Starting pre processing with " + file_name
        logger.info(msg)
        # check the PP control file (for now not blocking anything)
        if opf_compliance.check_pp_controlfile(cf_file):
            logger.info("")
        else:
            msg = "Error occurred checking compliance of PP controlfile"
            logger.error(msg)
        try:
            ds1 = do_retrieve_ds(pp_info, pfp_io.get_infilenamefromcf(cf_file))
            # write the processing level to a global attribute
            ds1.root["Attributes"]["processing_level"] = "PP"
            # apply linear corrections to the data
            pfp_ck.do_linear(cf_file, ds1)
            # create new variables using user defined functions
            pfp_ts.DoFunctions(ds1, pp_info["read_excel"])
            # calculate variances from standard deviations and vice versa
            pfp_ts.CalculateStandardDeviations(ds1)
            # check missing data and QC flags are consistent
            pfp_utils.CheckQCFlags(ds1)
            # apply corrections
            do_corrections(main_ui, cf_file, ds1)               
            msg = "Finished pre processing with " + file_name
            logger.info(msg)
            logger.info("")
        except Exception:
            msg = "Error occurred during pre processing in file " + file_name
            logger.error(msg)
            error_message = traceback.format_exc()
            logger.error(error_message)
            continue
    end = datetime.datetime.now()
    msg = " Finished pre processing at " + end.strftime("%Y%m%d%H%M")
    logger.info(msg)
    return


def get_all_recognized_corrections():
    return {"1": {"index": "1", "long_name": "Level 1 (unprocessed)", "short_name": "level_1", 
                  "aka": "Unprocessed", "description": "", "correction": ""},
            "2": {"index": "2", "long_name": "Level 2 (after despiking)", "short_name": "level_2", 
                  "aka": "Despike", "description": "", "correction": "Despike_"},
            "3": {"index": "3", "long_name": "Level 3 (after cross-wind correction)", "short_name": "level_3", 
                  "aka": "Cross-wind", "description": "", "correction": ""},
            "4": {"index": "4", "long_name": "Level 4 (after angle-of-attack correction", "short_name": "level_4",  
                  "aka": "Angle-of-Attack", "description": "", "correction": ""},
            "5": {"index": "5", "long_name": "Level 5 (after tilt correction)", "short_name": "level_5", 
                  "aka": "Tilt", "description": "", "correction": "Tilt_"},
            "6": {"index": "6", "long_name": "Level 6 (after time lag compensation)", "short_name": "level_6", 
                  "aka": "Time Lag", "description": "", "correction": "TimeLag_"},
            "7": {"index": "7", "long_name": "Level 7 (after detrending)", "short_name": "level_7", 
                  "aka": "Detrend", "description": "", "correction": "Detrend_"},
            "X": {"index": "X", "long_name": "Non-standard correction (unrecognized)", "short_name": "non-standard", "description": ""},}


def get_corrections_from_key_value(key, value):
    return {v.get(key, ""): v for _, v in get_all_recognized_corrections().items()}.get(value, {})


def convert_dataformat_to_regex(data_format):
    reg_ex = re.sub("\%[ymdMHS]", "[0-9]{2}", data_format)
    reg_ex = re.sub("\%[j]", "[0-9]{3}", reg_ex)
    reg_ex = re.sub("\%[Y]", "[0-9]{4}", reg_ex)
    reg_ex = "("+reg_ex+")"
    if re.findall("\%[A-z]", reg_ex):
        msg = "Date pattern " + ", ".join(re.findall("%[A-z]", reg_ex)) + " not recognized."
        logger.warn(msg)
    return reg_ex


def convert_ds_to_dataframe(ds, subset=[], how="outer"):
    variables_demanded = list(ds.root["Variables"].keys())
    if subset: variables_demanded = [c for c in subset if c in variables_demanded]
    if not variables_demanded:
        msg = "None of the requested variables exist."
        logger.warn(msg)
        return pandas.DataFrame()
    if [c for c in subset if c not in variables_demanded]:
        msg = "Columns " + ",".join([c for c in subset if c not in variables_demanded])
        msg = msg + "not found. Continuing with the rest..."
        logger.warn(msg)
    # pass into dataframe temporarilly
    dataframe = {}
    for v in variables_demanded:
        var_in = pfp_utils.GetVariable(ds, v)
        dataframe.update({v: var_in["Data"]})
    dataframe.update({"DateTime": var_in["DateTime"]})
    dataframe = pandas.DataFrame(dataframe)
    dataframe = dataframe.set_index("DateTime")
    return dataframe


def check_file_exits(file_name):
    if not os.path.isfile(file_name):
        msg = file_name + " not found."
        logger.error("")
        logger.error(msg)
        logger.error("")
        ok = 0
    else:
        ok = 1
    return ok
