from pygdbmi.gdbmiparser import parse_response
res = parse_response('&"Process record does not support instruction 0xd4000001 at address 0xfffff7c9a1c8.\\n"')
print(res)
