# calibre.utils.config_base shim.
class _Tweaks(dict):
    def __getattr__(self, name):
        return self.get(name)


tweaks = _Tweaks({})
