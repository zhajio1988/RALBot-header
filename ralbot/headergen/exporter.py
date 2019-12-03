import os
from systemrdl.node import AddressableNode, RootNode
from systemrdl.node import AddrmapNode, MemNode
from systemrdl.node import RegNode, RegfileNode, FieldNode

#===============================================================================
class headerGenExporter:
    def __init__(self, **kwargs):

        self.languages = kwargs.pop("languages", "verilog")
        self.headerFileContent = list()

        # Check for stray kwargs
        if kwargs:
            raise TypeError("got an unexpected keyword argument '%s'" % list(kwargs.keys())[0])

        if self.languages == "verilog":
            self.definePrefix = '`'
            self.hexPrefix = '\'h'
        elif self.languages == 'c' or self.languages == 'cpp':
            self.definePrefix = '#'
            self.hexPrefix = '0x'

        self.baseAddressName = ""
        self.filename = ""
        self.dirname = "."
        self.define = self.definePrefix + 'define '
        self.ifnDef = self.definePrefix + 'ifndef '
        self.ifDef = self.definePrefix + 'ifdef '
        self.endIf = self.definePrefix + 'endif'

    #---------------------------------------------------------------------------
    def export(self, node, path):
        # Make sure output directory structure exists
        if os.path.dirname(path):
            os.makedirs(os.path.dirname(path), exist_ok=True)
            self.dirname = os.path.split(path)[0]
        filename = os.path.basename(path)
        filename = os.path.splitext(filename)[0]
        if self.languages == "verilog":
            self.filename = filename + ".svh"
        elif self.languages == 'c' or self.languages == 'cpp':
            self.filename = filename + ".h"
        filename = self.filename.upper().replace('.', '_')
        self.genDefineMacro(filename)

        # If it is the root node, skip to top addrmap
        if isinstance(node, RootNode):
            node = node.top

        if not isinstance(node, AddrmapNode):
            raise TypeError("'node' argument expects type AddrmapNode. Got '%s'" % type(node).__name__)

        # Determine if top-level node should be exploded across multiple
        # addressBlock groups
        explode = False

        if isinstance(node, AddrmapNode):
            addrblockable_children = 0
            non_addrblockable_children = 0

            for child in node.children(unroll=False):
                if not isinstance(child, AddressableNode):
                    continue

                if isinstance(child, (AddrmapNode, MemNode)) and not child.is_array:
                    addrblockable_children += 1
                else:
                    non_addrblockable_children += 1

            if (non_addrblockable_children == 0) and (addrblockable_children >= 1):
                explode = True

        # Do the export!
        if explode:
            # top-node becomes the memoryMap
            # Top-node's children become their own addressBlocks
            for child in node.children(unroll=True):
                if not isinstance(child, AddressableNode):
                    continue
                self.add_addressBlock(child)
        else:
            # Not exploding apart the top-level node
            # Wrap it in a dummy memoryMap that bears it's name
            # Export top-level node as a single addressBlock
            self.add_addressBlock(node)

        self.headerFileContent.append("\n" + self.endIf)
        # Write out UVM RegModel file
        with open(os.path.join(self.dirname, self.filename), "w") as f:
            f.write('\n'.join(self.headerFileContent))
    
    #---------------------------------------------------------------------------
    def genDefineMacro(self, tag): 
        self.headerFileContent.append(self.ifnDef + " __%s__" % tag)
        self.headerFileContent.append(self.define + " __%s__\n" % tag)
    #---------------------------------------------------------------------------
    def add_content(self, content):
        self.headerFileContent.append(self.define + content)
    #---------------------------------------------------------------------------
    def add_addressBlock(self, node):

        self.add_content("%s 0" % ("%s_BASE_ADDR" % node.inst_name.upper()))   
        self.baseAddressName = ("`%s_BASE_ADDR" % node.inst_name.upper()) if self.languages == "verilog" else ("%s_BASE_ADDR" % node.inst_name.upper())

        for child in node.children():
            if isinstance(child, RegNode):
                self.add_register(node, child)
            elif isinstance(child, (AddrmapNode, RegfileNode)):
                self.add_registerFile(child)

    def add_registerFile(self, node):
        for child in node.children():
            if isinstance(child, RegNode):
                self.add_register(node, child)
            elif isinstance(child, (AddrmapNode, RegfileNode)):
                self.add_registerFile(child)
    #---------------------------------------------------------------------------
    def add_register(self, parent, node):
        X = "X``" if self.languages == "verilog" else "X"
        self.headerFileContent.append("//register: %s" % node.inst_name)
        if parent.is_array:
            regMacro = parent.inst_name.upper() + "_" + node.inst_name.upper() + "(X)" 
            self.add_content(regMacro + " %s + %s%x + %s*%s%x + %s%x" % (self.baseAddressName, self.hexPrefix, parent.raw_address_offset, X, self.hexPrefix, parent.array_stride, self.hexPrefix, node.address_offset)) 
        elif node.is_array:
            regMacro = parent.inst_name.upper() + "_" + node.inst_name.upper() + "(X)" 
            self.add_content(regMacro + " %s + %s%x + %s*%s%x" % (self.baseAddressName, self.hexPrefix, node.raw_address_offset, X, self.hexPrefix, node.array_stride))            
        else:
            regMacro = parent.inst_name.upper() + "_" + node.inst_name.upper()
            self.add_content(regMacro + " %s + %s%x" % (self.baseAddressName, self.hexPrefix, node.absolute_address))

        for field in node.fields():
            self.add_field(node, field)

    #---------------------------------------------------------------------------
    def add_field(self, parent, node):
        regFieldOffsetMacro = parent.inst_name.upper() + "_REG_" + node.inst_name.upper() + "_" + "OFFSET"
        self.add_content(regFieldOffsetMacro + " %d" % node.low)

        regFieldMaskMacro = parent.inst_name.upper() + "_REG_" + node.inst_name.upper() + "_" + "MASK"
        maskValue = hex(int('1' * node.width, 2) << node.low).replace("0x", "") 
        self.add_content(regFieldMaskMacro + " %s%s" % (self.hexPrefix, maskValue))

        #encode = node.get_property("encode")
        #if encode is not None:
        #    for enum_value in encode:
        #        print("debug point enum ", enum_value.name, enum_value.rdl_name, enum_value.rdl_desc)
        #        print("debug point ", "enum value", "'h%x" % enum_value.value)
