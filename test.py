import uuid

print(uuid.uuid4())

#from tronpy import Tron
from tronpy.providers import HTTPProvider

#client = Tron()  # Use mainnet(trongrid) with a single api_key

#s = client.get_latest_block_number()
#print(s)
#s = client.get_latest_block_id()
#print(s)
#s = client.get_account_balance(my_tt)
#print(s)
#shielded_trc20 = client.get_contract_as_shielded_trc20('TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t') #account_asset_balances(my_tt) #, 'TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t')
#print(s.trc20)
#print('Allowance:', shielded_trc20.trc20.functions.allowance(my_tt, shielded_trc20.shielded.contract_address))

#cntr = client.get_contract("TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t")

#print(dir(cntr.functions))  # prints list of contract functions

#for f in cntr.functions:
#    print(f)  # prints function signature(i.e. type info)

#print(cntr.functions.maximumFee())
#print(cntr.functions.symbol())
#print(cntr.functions.balanceOf(my_tt)/1000000)