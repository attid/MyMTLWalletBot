# Test Issues Found in routers/cheque.py

## Summary
While reviewing and fixing tests for `routers/cheque.py`, several bugs were discovered in the router code itself that prevent proper testing and likely cause runtime errors.

## Critical Issues Found

### 1. Missing `app_context` Parameter
Multiple functions use `app_context` variable but don't receive it as a parameter:

- **`cmd_cheque_show()` (line 102)**: Uses `app_context` on line 112 but doesn't have it as parameter
- **`get_kb_send_cheque()` (line 147)**: Uses `app_context` on lines 151-154 but doesn't have it as parameter  

These will cause `NameError: name 'app_context' is not defined` at runtime.

### 2. Missing Imports
The following functions are used but not imported (FIXED):
- ✅ `send_message` from `infrastructure.utils.telegram_utils`
- ✅ `clear_state` from `infrastructure.utils.telegram_utils`
- ✅ `eurmtl_asset` from `infrastructure.utils.stellar_utils`

### 3. Incorrect Repository Method Calls
- **`cb_cheque_click()` (line 271)**: Calls `repo.get_by_uuid(cheque_uuid, callback.from_user.id)` with 2 args, but the repository method signature only takes `uuid` as first parameter

### 4. Incorrect Use Case Initialization
- **`cmd_send_money_from_cheque()` (line 415)**: Creates `AddWallet(wallet_repo, encryption_service)` but `AddWallet.__init__()` only takes 1 argument (wallet_repository)

## Recommended Fixes

### Fix 1: Add app_context parameter to cmd_cheque_show
```python
async def cmd_cheque_show(session: Session, message: Message, state: FSMContext, app_context: AppContext):
```

### Fix 2: Add app_context parameter to get_kb_send_cheque  
```python
def get_kb_send_cheque(user_id: Union[types.CallbackQuery, types.Message, int], app_context: AppContext) -> types.InlineKeyboardMarkup:
```

And update all calls to this function to pass `app_context`.

### Fix 3: Fix repository method call
```python
# Line 271 - remove second parameter
cheque = await repo.get_by_uuid(cheque_uuid)
```

### Fix 4: Fix AddWallet initialization
```python
# Line 415 - remove encryption_service parameter
add_wallet_uc = AddWallet(wallet_repo)
```

## Test Strategy

Given these router bugs, the test file has been written to:
1. Mock the problematic functions to avoid runtime errors
2. Test the parts of the code that work correctly
3. Document which tests would fail due to router bugs

The tests are written according to established patterns but some will fail until the router bugs are fixed.
