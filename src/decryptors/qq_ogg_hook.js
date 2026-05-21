/**
 * Frida Hook 脚本 - QQ音乐 DRM 解密
 * 
 * Hook QQMusicCommon.dll 中的 EncAndDesMediaFile 类，
 * 利用其 Read() 方法获取解密后的音频数据。
 */

var TARGET_DLL = "QQMusicCommon.dll";

// 延迟初始化
var _initialized = false;
var _initError = null;
var _funcs = {};
var _CreateDirW = null;

function log(msg) {
    console.log("[QQ-OGG] " + msg);
}

function ensureCreateDirW() {
    if (_CreateDirW) return;
    try {
        var addr = Module.getExportByName("kernel32.dll", "CreateDirectoryW");
        if (addr) {
            _CreateDirW = new NativeFunction(addr, "bool", ["pointer", "pointer"]);
        }
    } catch (e) {
        log("CreateDirectoryW 不可用: " + e);
    }
}

function ensureInit() {
    if (_initialized) return;
    _initialized = true;

    log("正在查找 " + TARGET_DLL + "...");

    // 查找 DLL
    var dllFound = null;
    var modules = Process.enumerateModules();
    for (var i = 0; i < modules.length; i++) {
        if (modules[i].name.toLowerCase() === TARGET_DLL.toLowerCase()) {
            dllFound = modules[i];
            break;
        }
    }

    if (!dllFound) {
        log("未找到 " + TARGET_DLL);
        _initError = "未找到 " + TARGET_DLL + "，请确认 QQ 音乐版本";
        return;
    }

    log("找到 DLL: " + dllFound.name + " @ " + dllFound.base);

    // 枚举所有导出查找 EncAndDesMediaFile 相关函数
    var exports = [];
    try {
        exports = dllFound.enumerateExports();
    } catch (e) {
        log("枚举导出失败: " + e);
        _initError = "无法枚举 DLL 导出: " + e;
        return;
    }

    // 搜索目标函数
    var targetNames = {
        ctor: null,
        dtor: null,
        open: null,
        getSize: null,
        read: null
    };

    for (var j = 0; j < exports.length; j++) {
        var name = exports[j].name;
        if (name.indexOf("EncAndDesMediaFile") < 0) continue;
        
        // 优先选择实例方法（QAE = thiscall）而非静态方法（SA）
        if (name.indexOf("??0") === 0 && name.indexOf("ABV") < 0 && !targetNames.ctor) {
            targetNames.ctor = exports[j].address;
            log("找到 ctor: " + name);
        } else if (name.indexOf("??1") === 0 && !targetNames.dtor) {
            targetNames.dtor = exports[j].address;
            log("找到 dtor: " + name);
        } else if (name.indexOf("?Open@EncAndDesMediaFile@@QAE_NPB_W") === 0) {
            // 收集所有 Open 重载
            if (!targetNames.openAll) targetNames.openAll = [];
            targetNames.openAll.push({ name: name, address: exports[j].address });
            log("找到 Open 重载: " + name);
            // 默认使用第一个
            if (!targetNames.open) targetNames.open = exports[j].address;
        } else if (name.indexOf("?GetSize@EncAndDesMediaFile@@QAE") === 0 && !targetNames.getSize) {
            targetNames.getSize = exports[j].address;
            log("找到 GetSize (实例): " + name);
        } else if (name.indexOf("?Read@EncAndDesMediaFile@@QAE") === 0 && !targetNames.read) {
            targetNames.read = exports[j].address;
            log("找到 Read (实例): " + name);
        }
    }

    if (!targetNames.ctor || !targetNames.open || !targetNames.getSize || !targetNames.read) {
        _initError = "EncAndDesMediaFile 函数不完整";
        log("函数查找结果: ctor=" + !!targetNames.ctor + " open=" + !!targetNames.open + 
            " getSize=" + !!targetNames.getSize + " read=" + !!targetNames.read);
        return;
    }

    _funcs = targetNames;
    log("所有函数已就绪");
}

function ensureDir(pathStr) {
    ensureCreateDirW();
    if (!_CreateDirW) return;
    var parts = pathStr.split(/[\\/]/);
    var current = parts[0] === "" ? "\\" : parts[0];
    for (var i = 1; i < parts.length; i++) {
        current += "\\" + parts[i];
        try {
            var wide = Memory.allocUtf16String(current);
            _CreateDirW(wide, ptr(0));
        } catch (e) {}
    }
}

// RPC 接口
rpc.exports = {
    decrypt: function (srcFileName, dstFileName) {
        ensureInit();
        if (_initError) throw new Error(_initError);

        var Ctor = new NativeFunction(_funcs.ctor, "pointer", ["pointer"], "thiscall");
        var Dtor = new NativeFunction(_funcs.dtor, "void", ["pointer"], "thiscall");
        // 注意: 有两个 Open 重载:
        // ?Open@EncAndDesMediaFile@@QAE_NPB_WKKK@Z  -> (this, wchar*, uint, uint, uint)
        // ?Open@EncAndDesMediaFile@@QAE_NPB_W_N1@Z  -> (this, wchar*, bool, bool)
        // 我们使用第一个 (带3个额外参数的版本)
        var Ctor = new NativeFunction(_funcs.ctor, "pointer", ["pointer"], "thiscall");
        var Dtor = new NativeFunction(_funcs.dtor, "void", ["pointer"], "thiscall");
        var GetSize = new NativeFunction(_funcs.getSize, "uint32", ["pointer"], "thiscall");
        var Read = new NativeFunction(_funcs.read, "uint", ["pointer", "pointer", "uint32", "uint64"], "thiscall");

        var obj = Memory.alloc(0x28);
        Ctor(obj);
        try {
            var fileNameUtf16 = Memory.allocUtf16String(srcFileName);
            
            // 尝试所有 Open 重载，找到能正确解密的
            var openSuccess = false;
            var openVariants = _funcs.openAll || [{ name: "default", address: _funcs.open }];
            
            for (var oi = 0; oi < openVariants.length; oi++) {
                var variant = openVariants[oi];
                log("尝试 Open 重载: " + variant.name);
                
                // 构造不同的 Open 函数签名
                var Open;
                if (variant.name.indexOf("KKK") >= 0) {
                    // ?Open@EncAndDesMediaFile@@QAE_NPB_WKKK@Z -> (this, wchar*, uint32, uint32, uint32)
                    Open = new NativeFunction(variant.address, "uint8", ["pointer", "pointer", "uint32", "uint32", "uint32"], "thiscall");
                    var openResult = Open(obj, fileNameUtf16, 0, 0, 0);
                    log("Open(KKK) 返回: " + openResult);
                } else {
                    // ?Open@EncAndDesMediaFile@@QAE_NPB_W_N1@Z -> (this, wchar*, uint8, uint8)
                    Open = new NativeFunction(variant.address, "uint8", ["pointer", "pointer", "uint8", "uint8"], "thiscall");
                    var openResult = Open(obj, fileNameUtf16, 1, 0);
                    log("Open(bool) 返回: " + openResult);
                }
                
                if (!openResult) {
                    log("  Open 失败，跳过");
                    continue;
                }
                
                var fileSize = GetSize(obj);
                log("  GetSize: " + fileSize);
                
                if (fileSize > 0) {
                    // 检查是否解密了（读取前几个字节看是否还是加密的）
                    var testBuf = Memory.alloc(4);
                    Read(obj, testBuf, 4, 0);
                    var firstBytes = new Uint8Array(testBuf.readByteArray(4));
                    log("  前4字节: " + firstBytes[0].toString(16) + " " + firstBytes[1].toString(16) + 
                        " " + firstBytes[2].toString(16) + " " + firstBytes[3].toString(16));
                    
                    // 如果前4字节是 OggS (0x4f, 0x67, 0x67, 0x53)，说明解密成功
                    if (firstBytes[0] === 0x4f && firstBytes[1] === 0x67 && 
                        firstBytes[2] === 0x67 && firstBytes[3] === 0x53) {
                        log("  ** 解密成功! 数据以 OggS 开头 **");
                        openSuccess = true;
                        break;
                    }
                    // 如果前4字节是其他已知音频头
                    if ((firstBytes[0] === 0x49 && firstBytes[1] === 0x44 && firstBytes[2] === 0x33) || // ID3
                        (firstBytes[0] === 0x66 && firstBytes[1] === 0x4c && firstBytes[2] === 0x61 && firstBytes[3] === 0x43)) { // fLaC
                        log("  ** 解密成功! 检测到音频头 **");
                        openSuccess = true;
                        break;
                    }
                    log("  数据未解密，尝试下一个重载");
                }
            }
            
            if (!openSuccess) {
                throw new Error("无法正确解密文件。请确认:\n1. QQ 音乐已登录 VIP 账号\n2. 可以正常播放该歌曲\n3. QQ 音乐版本兼容");
            }

            var fileSize = GetSize(obj);
            log("最终文件大小: " + fileSize + " bytes");

            var buffer = Memory.alloc(fileSize);
            var bytesRead = Read(obj, buffer, fileSize, 0);
            if (bytesRead === 0) throw new Error("读取失败");
            log("已读取: " + bytesRead + " bytes");

            var lastSlash = dstFileName.lastIndexOf("\\");
            if (lastSlash !== -1) ensureDir(dstFileName.substring(0, lastSlash));

            var outFile = new File(dstFileName, "wb");
            outFile.write(buffer.readByteArray(bytesRead));
            outFile.flush();
            outFile.close();

            return bytesRead;
        } finally {
            Dtor(obj);
        }
    },

    probe: function () {
        ensureInit();
        return _initError === null;
    },

    getError: function () {
        ensureInit();
        return _initError;
    }
};