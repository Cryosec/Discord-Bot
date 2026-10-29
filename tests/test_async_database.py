"""AsyncDatabase: the sync Database calls run in worker threads under one limiter per bot."""
import asyncio
import inspect
import threading
import types

import pytest


def _bot():
    return types.SimpleNamespace()


def _facade(mod, bot):
    return mod.AsyncDatabase(bot)


def test_every_public_database_method_has_an_async_twin(real_db_module):
    mod = real_db_module
    public = {n for n, f in inspect.getmembers(mod.Database, inspect.isfunction)
              if not n.startswith("_")}
    own = {n for n, f in inspect.getmembers(mod.AsyncDatabase, inspect.isfunction)
           if not n.startswith("_")}
    # Cog hooks of Database come from commands.Cog, not from this module
    own_defined = {n for n in own if n in mod.AsyncDatabase.__dict__}
    sync_defined = {n for n in public if n in mod.Database.__dict__}
    assert sync_defined <= own_defined
    for name in sync_defined:
        assert inspect.iscoroutinefunction(getattr(mod.AsyncDatabase, name)), name
        assert (list(inspect.signature(getattr(mod.AsyncDatabase, name)).parameters)
                == list(inspect.signature(getattr(mod.Database, name)).parameters)), name


def test_call_runs_in_another_thread_and_returns_the_value(real_db_module):
    facade = _facade(real_db_module, _bot())
    seen = []

    def fake(user_id):
        seen.append(threading.get_ident())
        return [user_id]

    facade._db.getJacByID = fake

    async def go():
        return await facade.getJacByID("5")

    assert asyncio.run(go()) == ["5"]
    assert seen and seen[0] != threading.get_ident()


def test_errors_propagate_unchanged(real_db_module):
    facade = _facade(real_db_module, _bot())
    boom = real_db_module.mariadb.Error("down")
    facade._db.delJac = lambda user_id: (_ for _ in ()).throw(boom)

    async def go():
        await facade.delJac("5")

    with pytest.raises(real_db_module.mariadb.Error) as exc:
        asyncio.run(go())
    assert exc.value is boom


def test_limiter_is_on_the_bot_with_the_pool_size(real_db_module):
    bot = _bot()
    a, b = _facade(real_db_module, bot), _facade(real_db_module, bot)
    a._db.getJac = lambda: []

    async def go():
        await a.getJac()

    asyncio.run(go())
    assert bot.db_limiter._value == real_db_module.POOL_CONFIG["pool_size"]
    assert b._limiter() is a._limiter() is bot.db_limiter


def test_concurrency_never_exceeds_pool_size_across_facades(real_db_module):
    bot = _bot()
    size = real_db_module.POOL_CONFIG["pool_size"]
    facades = [_facade(real_db_module, bot) for _ in range(3)]
    lock = threading.Lock()
    state = {"now": 0, "peak": 0}
    release = threading.Event()

    def slow(*_args):
        with lock:
            state["now"] += 1
            state["peak"] = max(state["peak"], state["now"])
        release.wait(5)
        with lock:
            state["now"] -= 1
        return 1

    for f in facades:
        f._db.getJacByID = slow

    async def go():
        tasks = [asyncio.create_task(facades[i % 3].getJacByID("1")) for i in range(size * 3)]
        for _ in range(50):
            await asyncio.sleep(0.01)
        with lock:
            running = state["now"]
        release.set()
        await asyncio.gather(*tasks)
        return running

    running = asyncio.run(go())
    assert running == size
    assert state["peak"] == size


def test_cancelled_await_keeps_its_slot_until_the_thread_ends(real_db_module):
    bot = _bot()
    size = real_db_module.POOL_CONFIG["pool_size"]
    facade = _facade(real_db_module, bot)
    started = threading.Semaphore(0)
    release = threading.Event()

    def slow(*_args):
        started.release()
        release.wait(5)
        return 1

    facade._db.getJacByID = slow

    async def settle():
        for _ in range(20):
            await asyncio.sleep(0.01)

    async def go():
        tasks = [asyncio.create_task(facade.getJacByID("1")) for _ in range(size)]
        await settle()
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await settle()
        free_while_running = bot.db_limiter._value
        waiting = asyncio.create_task(facade.getJacByID("2"))
        await settle()
        blocked = not waiting.done()
        release.set()
        await waiting
        await settle()
        return free_while_running, blocked, bot.db_limiter._value

    free, blocked, after = asyncio.run(go())
    assert free == 0
    assert blocked
    assert after == size


def test_slot_is_released_after_an_error(real_db_module):
    bot = _bot()
    facade = _facade(real_db_module, bot)
    facade._db.getJac = lambda: (_ for _ in ()).throw(RuntimeError("x"))

    async def go():
        for _ in range(real_db_module.POOL_CONFIG["pool_size"] + 2):
            with pytest.raises(RuntimeError):
                await facade.getJac()
        await asyncio.sleep(0.01)

    asyncio.run(go())
    assert bot.db_limiter._value == real_db_module.POOL_CONFIG["pool_size"]


def test_limiter_survives_re_instantiating_the_cog(real_db_module):
    bot = _bot()
    first = _facade(real_db_module, bot)
    first._db.getJac = lambda: []

    async def go():
        await first.getJac()

    asyncio.run(go())
    limiter = bot.db_limiter
    second = _facade(real_db_module, bot)  # the cog after a cogwatch reload
    assert second._limiter() is limiter


def test_optional_argument_reaches_the_sync_method(real_db_module):
    facade = _facade(real_db_module, _bot())
    got = []
    facade._db.addJac = lambda *a, **k: got.append((a, k))

    async def go():
        await facade.addJac("1", "l", "d", guild_id="9")

    asyncio.run(go())
    assert got == [(("1", "l", "d", "9"), {})]
