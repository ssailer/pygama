import os
import numpy as np
from ..data_decoder.py import *
from pygama import lgdo
from .ch_group import *


class FCEventDecoder(DataDecoder):
    """
    decode FlashCam digitizer event data.
    """
    def __init__(self, *args, **kwargs):
        """
        """
        # these are read for every event (decode_event)
        self.decoded_values = {
            'packet_id': { # packet index in file
               'dtype': 'uint32',
             },
            'ievt': { # index of event
              'dtype': 'int32',
            },
            'timestamp': { # time since epoch
              'dtype': 'float64',
              'units': 's',
            },
            'runtime': { # time since beginning of file
              'dtype': 'float64',
              'units': 's',
            },
            'numtraces': { # number of triggered adc channels
              'dtype': 'int32',
            },
            'tracelist': { # list of triggered adc channels
              'dtype': 'int16',
              'datatype': 'array<1>{array<1>{real}}', # vector of vectors
              'length_guess': 16,
            },
            'baseline': { # fpga baseline
              'dtype': 'uint16',
            },
            'onboard_E': {  # fpga energy
              'dtype': 'uint16',
            },
            'channel': { # right now, index of the trigger (trace)
              'dtype': 'uint32',
            },
            'ts_pps': { # PPS timestamp in sec
              'dtype': 'int32',
            },
            'ts_ticks': { # clock ticks
            'dtype': 'int32',
              },
            'ts_maxticks': { # max clock ticks
              'dtype': 'int32',
            },
            'to_mu_sec': { # the offset in sec between the master and unix
              'dtype': 'int64',
            },
            'to_mu_usec': { # the offset in usec between master and unix
              'dtype': 'int32',
            },
            'to_master_sec': { # the calculated sec which must be added to the master
              'dtype': 'int64',
            },
            'to_dt_mu_usec': { # the delta time between master and unix in usec
              'dtype': 'int32',
            },
            'to_abs_mu_usec': { # the abs(time) between master and unix in usec
              'dtype': 'int32',
            },
            'to_start_sec': { # startsec
              'dtype': 'int64',
            },
            'to_start_usec': { # startusec
              'dtype': 'int32',
            },
            'dr_start_pps': { # start pps of the next dead window
              'dtype': 'float32',
            },
            'dr_start_ticks': { # start ticks of the next dead window
              'dtype': 'float32',
            },
            'dr_stop_pps': { # stop pps of the next dead window
              'dtype': 'float32',
            },
            'dr_stop_ticks': { # stop ticks of the next dead window
              'dtype': 'float32',
            },
            'dr_maxticks': { # maxticks of the dead window
              'dtype': 'float32',
            },
            'deadtime': { # current dead time calculated from deadregion (dr) fields. Give the total dead time if summed up.
              'dtype': 'float32',
            },
            'waveform': { # digitizer data
              'dtype': 'uint16',
              'datatype': 'waveform',
              'wf_len': 65532, # max value. override this before initializing buffers to save RAM
              'dt': 16, # override if a different clock rate is used
              'dt_units': 'ns',
              't0_units': 'ns',
            },
        }
        super().__init__(*args, **kwargs)
        self.skipped_channels = {}


    def get_decoded_values(self, channel=None): 
        # same for all channels
        return self.decoded_values


    def set_file_config(self, fc_config):
        """
        access FCIOConfig members once when each file is opened

        fc_config is a lgdo Struct extracted via
        fc_config = FCConfigDecoder.decode_config(fcio)
        """
        self.fc_config = fc_config
        self.decoded_values['waveform']['wf_len'] = self.fc_config['nsamples']


    def decode_packet(self, fcio, lgdo_tables, packet_id, verbose=False):
        """
        access FCIOEvent members for each event in the raw file
        """

        ievt      = fcio.eventnumber # the eventnumber since the beginning of the file
        timestamp = fcio.eventtime   # the time since epoch in seconds
        runtime   = fcio.runtime     # the time since the beginning of the file in seconds
        eventsamples = fcio.nsamples   # number of sample per trace
        numtraces = fcio.numtraces   # number of triggered adcs
        tracelist = fcio.tracelist   # list of triggered adcs
        traces    = fcio.traces      # the full traces for the event: (nadcs, nsamples)
        baselines = fcio.baseline    # the fpga baseline values for each channel in LSB
        energies  = fcio.daqenergy   # the fpga energy values for each channel in LSB
        ts_pps         = fcio.timestamp_pps
        ts_ticks       = fcio.timestamp_ticks
        ts_maxticks    = fcio.timestamp_maxticks
        to_mu_sec      = fcio.timeoffset_mu_sec
        to_mu_usec     = fcio.timeoffset_mu_usec
        to_master_sec  = fcio.timeoffset_master_sec
        to_dt_mu_usec  = fcio.timeoffset_dt_mu_usec
        to_abs_mu_usec = fcio.timeoffset_abs_mu_usec
        to_start_sec   = fcio.timeoffset_start_sec
        to_start_usec  = fcio.timeoffset_start_usec
        dr_start_pps   = fcio.deadregion_start_pps
        dr_start_ticks = fcio.deadregion_start_ticks
        dr_stop_pps    = fcio.deadregion_stop_pps
        dr_stop_ticks  = fcio.deadregion_stop_ticks
        dr_maxticks    = fcio.deadregion_maxticks
        deadtime       = fcio.deadtime

        # all channels are read out simultaneously for each event
        for iwf in tracelist:
            tbl = lgdo_tables
            if not isinstance(tbl, lh5.Table):
                if iwf not in lgdo_tables:
                    if iwf not in self.skipped_channels:
                        self.skipped_channels[iwf] = 0
                    self.skipped_channels[iwf] += 1
                    continue
                tbl = lgdo_tables[iwf]
            if eventsamples != tbl['waveform']['values'].nda.shape[1]:
                print('FCEventDecoder Warning: event wf length was',
                      eventsamples, 'when',
                      self.decoded_values['waveform']['wf_len'], 'were expected')
            ii = tbl.loc
            tbl['channel'].nda[ii] = iwf
            tbl['packet_id'].nda[ii] = packet_id
            tbl['ievt'].nda[ii] =  ievt
            tbl['timestamp'].nda[ii] =  timestamp
            tbl['runtime'].nda[ii] =  runtime
            tbl['numtraces'].nda[ii] =  numtraces
            tbl['tracelist'].set_vector(ii, tracelist)
            tbl['baseline'].nda[ii] = baselines[iwf]
            tbl['onboard_E'].nda[ii] = energies[iwf]
            tbl['ts_pps'].nda[ii]         = ts_pps
            tbl['ts_ticks'].nda[ii]       = ts_ticks
            tbl['ts_maxticks'].nda[ii]    = ts_maxticks
            tbl['to_mu_sec'].nda[ii]      = to_mu_sec
            tbl['to_mu_usec'].nda[ii]     = to_mu_usec
            tbl['to_master_sec'].nda[ii]  = to_master_sec
            tbl['to_dt_mu_usec'].nda[ii]  = to_dt_mu_usec
            tbl['to_abs_mu_usec'].nda[ii] = to_abs_mu_usec
            tbl['to_start_sec'].nda[ii]   = to_start_sec
            tbl['to_start_usec'].nda[ii]  = to_start_usec
            tbl['dr_start_pps'].nda[ii]   = dr_start_pps
            tbl['dr_start_ticks'].nda[ii] = dr_start_ticks
            tbl['dr_stop_pps'].nda[ii]    = dr_stop_pps
            tbl['dr_stop_ticks'].nda[ii]  = dr_stop_ticks
            tbl['dr_maxticks'].nda[ii]    = dr_maxticks
            tbl['deadtime'].nda[ii]       = deadtime
            waveform = traces[iwf]
            tbl['waveform']['values'].nda[ii][:] = waveform
            tbl.push_row()

        return 36*4 + numtraces*(1 + eventsamples + 2)*2