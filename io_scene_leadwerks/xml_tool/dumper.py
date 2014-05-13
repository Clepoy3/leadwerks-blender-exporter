# -*- coding: utf-8 -*-

from collections import OrderedDict
import sys
from leadwerks.mdl import constants
from leadwerks import streams
from lxml import etree


class MdlDumper(object):
    def __init__(self, path):
        self.reader = streams.BinaryStreamReader(path)
        self.reader.open()
        self.data = OrderedDict()

    def read(self):
        self.data = self.read_node()
        self.reader.close()

    def read_node(self):
        data, read_fn = self.read_header()
        data.update(read_fn())
        if data['num_kids']:
            data['blocks'] = []
        for i in range(0, data['num_kids']):
            data['blocks'].append(self.read_node())
        return data

    def read_header(self):
        node_code = self.reader.read_int()
        header = OrderedDict({
            'code': node_code,
            'num_kids': self.reader.read_int(),
            '_block_size': self.reader.read_int(),
            '_offset': self.reader.cur_pos(),
        })

        reader = self.get_node_reader(node_code)
        if not reader:
            print('ERROR! Block reader not found:', node_code)
            sys.exit(1)

        return header, reader

    def get_node_reader(self, node_code):
        amap = {
            str(constants.MDL_FILE): self.header_reader,
            str(constants.MDL_MESH): self.mesh_reader,
            str(constants.MDL_PROPERTIES): self.props_reader,
            str(constants.MDL_SURFACE): self.surface_reader,
            str(constants.MDL_VERTEXARRAY): self.vertex_array_reader,
            str(constants.MDL_INDICEARRAY): self.indices_reader,
            str(constants.MDL_BONE): self.bone_reader,
            str(constants.MDL_ANIMATIONKEYS): self.anim_reader,
            str(constants.MDL_NODE): self.node_reader,
        }
        return amap.get(str(node_code))

    def fmt_batch(self, data, modifier='s'):
        ret = []
        for d in data:
            ret.append(format(d, modifier))
        return ret

    def fmt_var_type(self, dt):
        var_type_map = {
            str(constants.MDL_FLOAT): 'FLOAT',
            str(constants.MDL_INT): 'INT',
            str(constants.MDL_UNSIGNED_BYTE): 'BYTE',
            str(constants.MDL_UNSIGNED_SHORT): 'SHORT',
        }
        return {'name': var_type_map.get(str(dt), 'UNKNOWN'), 'value': dt}

    def fmt_data_type(self, dt):
        data_type_map = {
            str(constants.MDL_POSITION): 'POSITION',
            str(constants.MDL_NORMAL): 'NORMAL',
            str(constants.MDL_TEXTURE_COORD): 'TEXTURE_COORD',
            str(constants.MDL_COLOR): 'COLOR',
            str(constants.MDL_TANGENT): 'TANGENT',
            str(constants.MDL_BINORMAL): 'BINORMAL',
            str(constants.MDL_BONEINDICE): 'BONEINDICE',
            str(constants.MDL_BONEWEIGHT): 'BONEWEIGHT',
        }

        return {'name': data_type_map.get(str(dt), 'UNKNOWN'), 'value': dt}

    def mesh_reader(self):
        ret = {
            'name': 'MESH',
            'matrix': self.fmt_batch(self.reader.read_batch('f', 16), 'f')
        }
        return ret

    def surface_reader(self):
        return {
            'name': 'SURFACE'
        }

    def header_reader(self):
        ret = {
            'name': 'FILE',
            'version': self.reader.read_int()
        }
        return ret

    def props_reader(self):
        count = self.reader.read_int()
        ret = OrderedDict()
        ret['name'] = 'PROPERTIES'
        ret['count'] = count
        ret['properties'] = []

        for i in range(0, count):
            ret['properties'].append({
                'name': self.reader.read_nt_str(),
                'value': self.reader.read_nt_str(),
            })
        return ret

    def vertex_array_reader(self):
        count = self.reader.read_int()
        ret = {
            'name': 'VERTEXARRAY',
            'number_of_vertices': count,
            'data_type': self.fmt_data_type(self.reader.read_int()),
            'variable_type': self.fmt_var_type(self.reader.read_int()),
            'elements_count': self.reader.read_int(),
        }
        vt = ret['variable_type']['value']
        mod = 'f' if vt == constants.MDL_FLOAT else 'H'

        if ret['data_type']['name'] in ['COLOR', 'BONEINDICE', 'BONEWEIGHT']:
            ret['elements_count'] = 4
            mod = 'B'

        ret['data'] = self.reader.read_batch(
            mod,
            ret['elements_count'] * ret['number_of_vertices']
        )

        return ret

    def indices_reader(self):
        count = self.reader.read_int()
        ret = {
            'name': 'INDICEARRAY',
            'number_of_indexes': count,
            'primitive_type': self.reader.read_int(),
            'variable_type': self.fmt_var_type(self.reader.read_int()),
            'data': self.reader.read_batch('H', count)
        }
        return ret

    def bone_reader(self):
        ret = {
            'name': 'BONE',
            'matrix': self.fmt_batch(self.reader.read_batch('f', 16), 'f'),
            'bone_id': self.reader.read_int()
        }
        return ret

    def node_reader(self):
        ret = {
            'name': 'NODE',
            'matrix': self.fmt_batch(self.reader.read_batch('f', 16), 'f'),
        }
        return ret

    def anim_reader(self):
        ret = OrderedDict({'name': 'ANIMATIONKEYS'})
        ret['number_of_frames'] = self.reader.read_int()
        ret['frames'] = []

        for i in range(0, ret['number_of_frames']):
            ret['frames'].append(
                self.reader.read_batch('f', 16)
            )

        return ret

    def as_xml(self):
        return self.__convert_node_to_xml(self.data)

    def __convert_node_to_xml(self, node):
        # list of parameters displayed as xml attributes of block
        attrs = ['name', '_num_kids', '_block_size', '_offset', 'code']

        xml = '<block'
        for k in attrs:
            v = node.get(k)
            if v:
                xml = '%s %s="%s"' % (xml, k, v)
        xml = '%s>' % xml

        for k, v in node.items():
            if k == 'blocks' or k in attrs:
                continue
            if type(v) is list:
                if not v:
                    continue

                res = ''
                if type(v[0]) is dict or type(v[0]) is OrderedDict:
                    for iv in v:
                        res = '%s%s' % (res, self.__fmt_kv(iv))

                # animation frames list
                if type(v[0]) is list:
                    for l in v:
                        res = '%s<frame>%s</frame>' % (res, ', '.join(map(str, l)))

                if not res:
                    res = ','.join(map(str, v))
                v = res
            elif type(v) is dict or type(v) is OrderedDict:
                v = self.__fmt_kv(v)
            xml = '%s<%s>%s</%s>' % (xml, k, v, k)

        # recursive calls to add children blocks
        if node.get('blocks'):
            xml = '%s<subblocks>' % xml
            for n in node['blocks']:
                xml = '%s%s' % (xml, self.__convert_node_to_xml(n))
            xml = '%s</subblocks>' % xml

        xml = '%s</block>' % xml

        parser = etree.XMLParser(remove_blank_text=True)
        tree = etree.fromstring(xml, parser)
        return etree.tostring(tree, pretty_print=True).decode(encoding='UTF-8')

    def __fmt_kv(self, v):
        """
        Formatting key/value pairs
        """
        if v.get('value'):
            v = '<value means="%s">%s</value>' % (v.get('name'), v.get('value'))
        return v