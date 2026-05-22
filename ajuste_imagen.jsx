/*******************************************************************************
 *
 * Nombre: Procesar_SKUs_Por_Carpeta.jsx
 * Propósito: Lee una carpeta raíz que contiene subcarpetas de SKUs.
 *            Por cada subcarpeta, carga las imágenes (PNG/JPG/TIFF) en las
 *            mesas de trabajo del documento activo, las redimensiona a 597px
 *            de alto, las centra, y exporta cada mesa de trabajo como JPG
 *            en una carpeta de salida. Procesa una subcarpeta a la vez para
 *            no trabar Illustrator.
 *
 * REQUISITOS:
 *   - Tener un documento de Illustrator abierto con al menos tantas mesas
 *     de trabajo como imágenes tenga la subcarpeta más grande (recomendado: 5).
 *   - Las imágenes en cada subcarpeta deben ser: JPG, PNG, TIFF o PSD.
 *
 ******************************************************************************/

#target illustrator
#targetengine main
#script "Procesar_SKUs_Por_Carpeta"

// ============================================================
//  CONFIGURACIÓN — ajustá estos valores si es necesario
// ============================================================
var CONFIG = {
    targetHeight   : 597,          // Alto final de cada imagen (px)
    jpgQuality     : 100,          // Calidad JPG exportado (0–100)
    outputFolderName: "_EXPORTADOS" // Nombre de la carpeta de salida (se crea dentro de la raíz)
};
// ============================================================

// --- Extensiones de imagen aceptadas ---
var VALID_EXTENSIONS = ["jpg", "jpeg", "png", "tif", "tiff", "psd", "ai", "pdf"];

// ============================================================
//  FUNCIÓN PRINCIPAL
// ============================================================
function main() {

    // 1. Verificar documento abierto
    if (app.documents.length === 0) {
        alert("Error: Abrí un documento de Illustrator antes de correr este script.");
        return;
    }
    var doc = app.activeDocument;

    // 2. El usuario elige la carpeta raíz
    var rootFolder = Folder.selectDialog("Seleccioná la carpeta raíz que contiene las subcarpetas de SKUs:");
    if (!rootFolder) {
        alert("Operación cancelada.");
        return;
    }

    // 3. Leer subcarpetas (= SKUs)
    var skuFolders = getSubFolders(rootFolder);
    if (skuFolders.length === 0) {
        alert("No se encontraron subcarpetas dentro de:\n" + rootFolder.fsName);
        return;
    }

    // 4. Crear carpeta de salida
    var outputFolder = new Folder(rootFolder.fsName + "/" + CONFIG.outputFolderName);
    if (!outputFolder.exists) {
        outputFolder.create();
    }

    // 5. Informar al usuario
    var proceed = confirm(
        "Se encontraron " + skuFolders.length + " carpetas de SKUs.\n\n" +
        "Las imágenes ajustadas se exportarán como JPG en:\n" +
        outputFolder.fsName + "\n\n" +
        "¿Continuar?"
    );
    if (!proceed) return;

    // 6. Procesar cada SKU
    var totalExported = 0;
    var errors = [];

    for (var s = 0; s < skuFolders.length; s++) {
        var skuFolder = skuFolders[s];
        var skuName   = skuFolder.name;

        // Obtener imágenes válidas dentro de la subcarpeta
        var imageFiles = getImageFiles(skuFolder);

        if (imageFiles.length === 0) {
            errors.push("Sin imágenes: " + skuName);
            continue;
        }

        // Verificar mesas de trabajo suficientes
        if (doc.artboards.length < imageFiles.length) {
            errors.push(
                skuName + ": necesita " + imageFiles.length +
                " mesas de trabajo, el doc solo tiene " + doc.artboards.length
            );
            continue;
        }

        // Crear subcarpeta de salida para este SKU
        var skuOutputFolder = new Folder(outputFolder.fsName + "/" + skuName);
        if (!skuOutputFolder.exists) {
            skuOutputFolder.create();
        }

        // Procesar cada imagen del SKU
        for (var i = 0; i < imageFiles.length; i++) {
            try {
                var imgFile  = imageFiles[i];
                var artboard = doc.artboards[i];

                // Activar mesa de trabajo
                doc.artboards.setActiveArtboardIndex(i);

                // --- Abrir la imagen como documento temporal ---
                var openOpts = new OpenOptions();
                var tempDoc  = app.open(imgFile, DocumentColorSpace.RGB, openOpts);

                // Seleccionar todo y copiar
                tempDoc.selectObjectsOnActiveArtboard();
                app.copy();

                // Cerrar el documento temporal sin guardar
                tempDoc.close(SaveOptions.DONOTSAVECHANGES);

                // Pegar en el documento principal
                app.activeDocument = doc;
                app.paste();
                app.redraw();

                // Obtener el item recién pegado (estará seleccionado)
                var pastedItems = doc.selection;
                if (!pastedItems || pastedItems.length === 0) {
                    throw new Error("No se pudo pegar la imagen");
                }

                // Si se pegaron varios items, agruparlos
                var placedItem;
                if (pastedItems.length === 1) {
                    placedItem = pastedItems[0];
                } else {
                    placedItem = doc.groupItems.add();
                    for (var pi = 0; pi < pastedItems.length; pi++) {
                        pastedItems[pi].moveToBeginning(placedItem);
                    }
                }

                app.redraw();

                // --- Redimensionar a targetHeight ---
                var originalHeight = placedItem.height;
                if (originalHeight > 0) {
                    var scalePercent = (CONFIG.targetHeight / originalHeight) * 100;
                    placedItem.resize(scalePercent, scalePercent, true, true, true, true, false);
                    app.redraw();
                }

                // --- Centrar en la mesa de trabajo ---
                var abRect = artboard.artboardRect;
                var abLeft = abRect[0];
                var abTop  = abRect[1];
                var abW    = abRect[2] - abLeft;
                var abH    = abTop - abRect[3];
                var abCX   = abLeft + (abW / 2);
                var abCY   = abTop  - (abH / 2);

                var iW = placedItem.width;
                var iH = placedItem.height;
                placedItem.position = [abCX - (iW / 2), abCY + (iH / 2)];

                // --- Exportar mesa de trabajo como JPG ---
                var baseName   = imgFile.name.replace(/\.[^\.]+$/, "");
                var exportFile = new File(skuOutputFolder.fsName + "/" + baseName + ".jpg");

                exportArtboardAsJPG(doc, i, exportFile);

                // --- Limpiar: eliminar el item del documento ---
                placedItem.remove();
                app.redraw();

                totalExported++;

            } catch (eImg) {
                errors.push(skuName + " / " + imageFiles[i].name + ": " + eImg.message);
            }
        }
    }

    // 7. Resultado final
    var msg = "¡Proceso completado!\n\n" +
              "Imágenes exportadas: " + totalExported + "\n" +
              "Carpeta de salida: " + outputFolder.fsName;

    if (errors.length > 0) {
        msg += "\n\n⚠ Errores (" + errors.length + "):\n" + errors.join("\n");
    }

    alert(msg);
}

// ============================================================
//  FUNCIÓN: Exportar una mesa de trabajo específica como JPG
// ============================================================
function exportArtboardAsJPG(doc, artboardIndex, destFile) {
    doc.artboards.setActiveArtboardIndex(artboardIndex);

    var exportOpts              = new ExportOptionsJPEG();
    exportOpts.artBoardClipping = true;   // Recortar exactamente a la mesa de trabajo
    exportOpts.qualitySetting   = 100;    // Maxima calidad
    exportOpts.antiAliasing     = true;
    exportOpts.resolution       = 300;    // 300 DPI — evita la degradacion a 72 DPI por defecto

    doc.exportFile(destFile, ExportType.JPEG, exportOpts);
}

// ============================================================
//  FUNCIÓN: Obtener subcarpetas directas de una carpeta
// ============================================================
function getSubFolders(parentFolder) {
    var items    = parentFolder.getFiles();
    var folders  = [];
    for (var i = 0; i < items.length; i++) {
        if (items[i] instanceof Folder) {
            // Ignorar carpeta de salida si ya existe
            if (items[i].name !== CONFIG.outputFolderName) {
                folders.push(items[i]);
            }
        }
    }
    // Ordenar alfabéticamente por nombre
    folders.sort(function(a, b) {
        return a.name.toLowerCase() < b.name.toLowerCase() ? -1 : 1;
    });
    return folders;
}

// ============================================================
//  FUNCIÓN: Obtener archivos de imagen válidos dentro de una carpeta
// ============================================================
function getImageFiles(folder) {
    var items  = folder.getFiles();
    var images = [];
    for (var i = 0; i < items.length; i++) {
        if (items[i] instanceof File) {
            var ext = getExtension(items[i].name).toLowerCase();
            if (isValidExtension(ext)) {
                images.push(items[i]);
            }
        }
    }
    // Ordenar por nombre
    images.sort(function(a, b) {
        return a.name.toLowerCase() < b.name.toLowerCase() ? -1 : 1;
    });
    return images;
}

// ============================================================
//  UTILIDADES
// ============================================================
function getExtension(filename) {
    var parts = filename.split(".");
    return parts.length > 1 ? parts[parts.length - 1] : "";
}

function isValidExtension(ext) {
    for (var i = 0; i < VALID_EXTENSIONS.length; i++) {
        if (VALID_EXTENSIONS[i] === ext) return true;
    }
    return false;
}

// ============================================================
//  EJECUTAR
// ============================================================
try {
    main();
} catch(e) {
    alert("Error inesperado: " + e.message + "\n\nLínea: " + e.line);
}