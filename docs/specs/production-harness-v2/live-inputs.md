# Live inputs — production-harness-v2

Minted at ticket 226 by that ticket's review cycle 1, not by the walking
skeleton's session. Ticket 166 priced this effort's layout wall and its RULE
declined this file along with the 231-file path move; cycle 1 found the PRICE
covers only the path move, and 226 is the first ticket in the effort to leave a
live far end worth recording. So the file starts here. The 225 tickets before
it are not recorded as having had no live inputs -- they are recorded nowhere,
which is the wall 166 priced.

## 226
INPUT           Two impact replays through a real `proxy.listen` door on
                127.0.0.1, under a leased Identity opened from real sealed
                ciphertext, each after an operator `answer_decision` on the
                `rk2_human` connection. Cluster `rk2-test-pg` on
                127.0.0.1:55433, `RK_TEST_DATABASE=rk2_t226`.
FAR END         `pivot_stamps` = 2 and `chains` = 1 on a Program that held
                neither, the chain composing 2 steps over 1 edge, and
                `check_kill_chains()` returning no rows over it. The first
                execution of `redkraken.replay::_downstream` in this
                repository.
STATUS          promoted to tests.test_database.RuntimeChainTest
REPLAYS         0 ()
