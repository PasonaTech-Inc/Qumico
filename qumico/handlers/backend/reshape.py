from inspect import cleandoc
import logging

import numpy as np

from onnx.backend.base import namedtupledict

from qumico.handlers.backend_handler import BackendHandler
from qumico.handlers.handler import onnx_op
from qumico.common import c_helper
from qumico.common import data_type


@onnx_op('Reshape')
class Reshape(BackendHandler):

    @classmethod
    def instantiate(cls, node, **kwargs):
        input_data1 = node.input_tensor[0]
        input_data2 = node.input_tensor[1]

        try:
            # numpy reshape is not allowed to set zero dim in its's shape 
            # zero dim in onnx spec means the same dim 
            input_data2_to_np = [input_data1.shape[index] if d == 0 else d  for (index, d) in enumerate(input_data2)]
            outputs_shape = np.reshape(input_data1, input_data2_to_np).shape
            
        except TypeError as e:
            input_data2_shape = input_data2.shape
            if input_data2_shape[-1] == 1:
                logging.warn('assume shape automatically in reshape op because of shape error:{0}'.format(e))
                outputs_shape = np.reshape(input_data1, np.squeeze(input_data2, axis=-1)).shape
            else:
                raise ValueError()
        except Exception as e:
            logging.warn('use model output shape in reshape op because of shape error:{0}'.format(e))
            outputs_shape = node.outputs_info[0][1]

        outputs_dtype = input_data1.dtype
        outputs_dict = {node.valid_var_name(node.outputs[0]): np.ones(shape=outputs_shape, dtype=outputs_dtype)}
        output_tensor = namedtupledict('output_tensor', outputs_dict.keys())(**outputs_dict)
        return cls(node, input_tensor=node.input_tensor, 
                   output_tensor=output_tensor, attrs=node.attrs)

    @classmethod
    def get_param_type_name(cls):
        return 'ReshapeOpParam'

    @classmethod
    def get_c_op_file_name(cls):
        return ['reshape.c']


    @classmethod
    def get_c_op_include_header(cls):
        return []
    

    @classmethod
    @BackendHandler.dec_generate_once()
    def get_c_param_type(cls):
        return cleandoc(
            '''
            typedef struct {
                char* name;
            } ReshapeOpParam;
            ''')


    def generate_c_code(self, **kwargs):
        res =''
        res += '\n'.join([c_helper.generate_local_include(h) for h in self.get_c_op_include_header()])
        res +='\n\n'

        # param type
        res += self.get_c_param_type()
        res +='\n\n'

        # 1
        # 2
        TemplateStatements = '''
            {t} *_data = ({t} *)data;
            {t} *_reshaped = ({t} *)reshaped;

            int     data_elements = {data_elements};
            int     shape_elements = {shape_elements};
            int     i;

            if (data_elements >= shape_elements) {{
                for (i=0; i<shape_elements; i++) {{
                    *(_reshaped +i) = *(_data +i);
                }}
            }} else {{
                for (i=0; i<data_elements; i++) {{
                    *(_reshaped +i) = *(_data +i);
                }}
                for (; i<shape_elements; i++) {{
                    *(_reshaped +i) = ({t})0.0;
                }}
            }}
        '''

        mapping = {}
        mapping.update({'t': data_type.np2c(self.output_tensor_dtypes[0])})
        mapping.update({'data_elements': self.input_tensor[0].size})
        mapping.update({'shape_elements': self.output_tensor[0].size})


        # 3        
        TemplateFunction = cleandoc('''
        void {op_func_name}(void *op_param, {t} data{dims_data}, long long int shape[], {t} reshaped{dims_reshaped}, void *inputs_params, void* outputs_params) {{
            {statements}
        }}
        ''')

        mappingf = {}
        mappingf.update({'op_func_name': self.get_func_name()})
        mappingf.update({'dims_data': c_helper.generate_dim_bracket(self.input_tensor_shapes[0])}) 
        mappingf.update({'dims_reshaped': c_helper.generate_dim_bracket(self.output_tensor_shapes[0])}) 
        mappingf.update({'t': data_type.np2c(self.output_tensor_dtypes[0])})
        mappingf.update({'statements': TemplateStatements.format(**mapping)})
        res += '\n\n'
        res += TemplateFunction.format(**mappingf)

        return res


    def gen_op_variables(self, node, node_num, **kwargs):
        TemplateVariavbles = cleandoc('''
            int OpShapeNode{node_num}[] = {{{shape}}};
            int OutputShapeNode{node_num}[] = {{{shape}}};
            ''')
        ndim = self.output_tensor_ndims[0]
        shape = self.output_tensor_shapes[0]

        mapping = {}
        mapping.update({'shape': ','.join(map(str,shape[:ndim]))})
        mapping.update({'node_num': str(node_num)})

        return TemplateVariavbles.format(**mapping)        


    def gen_init_func(self, node, node_num, indent=4, **kwargs):

        TemplateInitFunc=cleandoc('''
        {indent}// define input & output
        {indent}Nodes[{node_num}].op_param = &{node_param_name};
        {indent}Nodes[{node_num}].outputs = &{output_val_name};
        {indent}Nodes[{node_num}].output_ndim = {ndim};
        {indent}Nodes[{node_num}].output_shape = OutputShapeNode{node_num};
        ''')
        
        mapping = {}
        mapping.update({'node_param_name': node.node_param_name})
        mapping.update({'node_num': str(node_num)})
        mapping.update({'add_name': self.get_name()})
        mapping.update({'ndim':str(self.output_tensor_ndims[0])})
        mapping.update({'output_val_name': self.output_tensor_names[0]})
        mapping.update({'indent':' ' * indent})

        return TemplateInitFunc.format(**mapping)

  
    @classmethod
    def version_5(cls, node, **kwargs):
        return cls.instantiate(node, **kwargs)
