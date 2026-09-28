import { isNative } from "./platform.js";

const FOLDER = "offline";
const DB_NAME = "pedagogue-offline";
const STORE = "kv";

function fileFor(key) {
  let hash = 2166136261;
  for (const char of key) {
    hash ^= char.codePointAt(0);
    hash = Math.imul(hash, 16777619);
  }
  return `${FOLDER}/${(hash >>> 0).toString(36)}-${key.length}.json`;
}

let filesystem = null;

function loadFilesystem() {
  if (!filesystem) filesystem = import("@capacitor/filesystem");
  return filesystem;
}

const nativeStore = {
  async get(key) {
    try {
      const { Filesystem, Directory, Encoding } = await loadFilesystem();
      const { data } = await Filesystem.readFile({ path: fileFor(key), directory: Directory.Data, encoding: Encoding.UTF8 });
      const record = JSON.parse(data);
      return record.key === key ? record.value : undefined;
    } catch {
      return undefined;
    }
  },
  async set(key, value) {
    try {
      const { Filesystem, Directory, Encoding } = await loadFilesystem();
      await Filesystem.writeFile({
        path: fileFor(key),
        directory: Directory.Data,
        encoding: Encoding.UTF8,
        recursive: true,
        data: JSON.stringify({ key, value, savedAt: Date.now() }),
      });
      return true;
    } catch {
      return false;
    }
  },
  async remove(key) {
    try {
      const { Filesystem, Directory } = await loadFilesystem();
      await Filesystem.deleteFile({ path: fileFor(key), directory: Directory.Data });
    } catch {
      return false;
    }
    return true;
  },
  async clear() {
    try {
      const { Filesystem, Directory } = await loadFilesystem();
      await Filesystem.rmdir({ path: FOLDER, directory: Directory.Data, recursive: true });
    } catch {
      return false;
    }
    return true;
  },
};

let database = null;

function openDatabase() {
  if (!database) {
    database = new Promise((resolve, reject) => {
      const request = indexedDB.open(DB_NAME, 1);
      request.onupgradeneeded = () => request.result.createObjectStore(STORE);
      request.onsuccess = () => resolve(request.result);
      request.onerror = () => reject(request.error);
    });
    database.catch(() => {
      database = null;
    });
  }
  return database;
}

async function transact(mode, action) {
  const db = await openDatabase();
  return new Promise((resolve, reject) => {
    const transaction = db.transaction(STORE, mode);
    const request = action(transaction.objectStore(STORE));
    transaction.oncomplete = () => resolve(request.result);
    transaction.onerror = () => reject(transaction.error);
    transaction.onabort = () => reject(transaction.error);
  });
}

const webStore = {
  get: (key) => transact("readonly", (store) => store.get(key)).catch(() => undefined),
  set: (key, value) => transact("readwrite", (store) => store.put(value, key)).then(() => true, () => false),
  remove: (key) => transact("readwrite", (store) => store.delete(key)).then(() => true, () => false),
  clear: () => transact("readwrite", (store) => store.clear()).then(() => true, () => false),
};

const memory = new Map();

const memoryStore = {
  get: async (key) => memory.get(key),
  set: async (key, value) => memory.set(key, value) && true,
  remove: async (key) => memory.delete(key),
  clear: async () => {
    memory.clear();
    return true;
  },
};

export const deviceStore = isNative ? nativeStore : typeof indexedDB === "undefined" ? memoryStore : webStore;
