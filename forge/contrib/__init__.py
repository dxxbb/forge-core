"""`forge.contrib` — 示范用 adapter，不自动注册到 core。

一个新 runtime 的适配器大约 20 行代码，写完 `register_adapter(YourAdapter())`
就能用。这里放了几个常见 runtime 的 reference 实现，既是文档也是你 fork
的起点。

用法：

    from forge.contrib.cursor import CursorAdapter
    from forge.targets import register_adapter
    register_adapter(CursorAdapter())
    # 之后 config 里 target: cursor 就走这个适配器
"""
