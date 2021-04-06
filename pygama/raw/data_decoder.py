"""
data_decoder.py

base classe for decoding data into raw lgdo tables / files
"""

from abc import ABC
import numpy as np
from pygama import lgdo


class DataDecoder(ABC):
    """Decodes packets from a data stream

    The values that get decoded need to be described by a dict called
    'decoded_values' that helps determine how to set up the buffers and write
    them to file. lgdo Tables are made whose columns correspond to the elements
    of decoded_values, and packet data gets pushed to the end of the table one
    row at a time. See FlashCamEventDecoder or ORCAStruck3302 for an example.

    Some decoders (like for file headers) may not need to push to a table, so they
    do not need decoded_values. Such classes should still derive from
    DataDecoder in anticipation of future functionality

    Subclasses should define a method for decoding data to a buffer like
    decode_packet(packet, data_buffer, packet_id, verbose=False)

    Garbage collection writes binary data as an array of uint32s to a
    variable-length array in the output file. If a problematic packet is found,
    call put_in_garbage(packet). User should set up an enum or bitbank of garbage
    codes to be stored along with the garbage packets.
    """
    def __init__(self, garbage_length=256, packet_size_guess=1024):
        self.garbage_table = lgdo.Table(garbage_length)
        shape_guess=(garbage_length, packet_size_guess)
        self.garbage_table.add_field('packets',
                                     lgdo.VectorOfVectors(shape_guess=shape_guess, dtype='uint8'))
        self.garbage_table.add_field('packet_id',
                                     lgdo.Array(shape=garbage_length, dtype='uint32'))
        # TODO: add garbage codes enum attribute: user supplies in constructor
        # before calling super()
        self.garbage_table.add_field('garbage_code',
                                     lgdo.Array(shape=garbage_length, dtype='uint32'))


    def get_decoded_values(self, key=None):
        """ Get decoded values (optionally for a given key, typically a channel)

        Must overload for your decoder if it has key-specific decoded
        values. Note: implement key = None returns a "default" decoded_values

        Otherwise, just returns self.decoded_values, which should be defined in
        the constructor
        """
        if key is None:
            return self.decoded_values if hasattr(self, decoded_values) else None
        name = type(self).__name__
        print("You need to implement key-specific get_decoded_values for", name)
        return None


    def initialize_lgdo_table(self, table, key=None):
        """ Initialize an lgdo Table based on decoded_values.
        key is typically the channel according to ch_group
        """
        if not hasattr(self, 'decoded_values'):
            name = type(self).__name__
            print(name, 'Error: no decoded_values available for setting up buffer')
            return
        dec_vals = self.get_decoded_values(key)
        size = table.size
        for field, fld_attrs in dec_vals.items():
            # make a copy of fld_attrs: pop off the ones we use, then keep any
            # remaining user-set attrs and store into the lgdo
            attrs = fld_attrs.copy()

            # get the dtype
            if 'dtype' not in attrs:
                name = type(self).__name__
                print(name, 'Error: must specify dtype for', field)
                continue
            dtype = attrs.pop('dtype')

            # no datatype: just a "normal" array
            if 'datatype' not in attrs:
                # allow to override "kind" for the dtype for lgdo
                if 'kind' in attrs:
                    attrs['datatype'] = 'array<1>{' + attrs.pop('kind') + '}'
                table.add_field(field, lgdo.Array(shape=size, dtype=dtype, attrs=attrs))
                continue

            # get datatype for complex objects
            datatype = attrs.pop('datatype')

            # waveforms: must have attributes t0_units, dt, dt_units, wf_len
            if datatype == 'waveform':
                t0_units = attrs.pop('t0_units')
                dt = attrs.pop('dt')
                dt_units = attrs.pop('dt_units')
                wf_table = lgdo.WaveformTable(size=size,
                                              t0=0, t0_units=t0_units,
                                              dt=dt, dt_units=dt_units,
                                              wf_len=wf_len, dtype=dtype,
                                              attrs=attrs)
                table.add_field(field, wf_table)
                continue

            # Parse datatype for remaining lgdos
            datatype, shape, elements = lgdo.parse_datatype(datatype)

            # ArrayOfEqualSizedArrays
            if datatype == 'array_of_equalsized_arrays':
                length = attrs.pop('length')
                # only arrays of 1D arrays are supported at present
                dims = (1,1)
                aoesa = lgdo.ArrayOfEqualSizedArrays(shape=(size,length), dtype=dtype, dims=dims, attrs=attrs)
                table.add_field(field, aoesa)
                continue

            # VectorOfVectors
            if elements.startswith('array'):
                length_guess = size
                if 'length_guess' in attrs: length_guess = attrs.pop('length_guess')
                vov = lgdo.VectorOfVectors(shape_guess=(size,length_guess), dtype=dtype, attrs=attrs)
                table.add_field(field, vov)
                continue

            # if we get here, got a bad datatype
            name = type(self).__name__
            print(name, 'Error: do not know how to make a', datatype, 'for', field)


    def put_in_garbage(self, packet, packet_id, code):
        i_row = self.garbage_table.loc
        p8 = np.frombuffer(packet, dtype='uint8')
        self.garbage_table['packets'].set_vector(i_row, p8)
        self.garbage_table['packet_id'].nda[i_row] = packet_id
        self.garbage_table['garbage_codes'].nda[i_row] = code
        self.garbage_table.push_row()


    def write_out_garbage(self, filename, group='/', lh5_store=None):
        if lh5_store is None: lh5_store = lgdo.LH5Store()
        n_rows = self.garbage_table.loc
        if n_rows == 0: return
        lh5_store.write_object(self.garbage_table, 'garbage', filename, group, n_rows=n_rows, append=True)
        self.garbage_table.clear()


