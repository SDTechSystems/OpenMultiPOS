# Preparar la máquina virtual de aceptación

La máquina prevista se llama OpenMultiPOS-QA. Crear la máquina no instala Windows. Estos pasos se realizan en el computador Windows que aloja Hyper-V; no cambian la instalación operativa de OpenMultiPOS.

1. Busca Administrador de Hyper-V en Inicio, haz clic derecho y elige Ejecutar como administrador. Selecciona el computador local y OpenMultiPOS-QA. La administración requiere permisos de Administradores o Administradores de Hyper-V. Si no aparece la herramienta, revisa la [instalación oficial de Hyper-V](https://learn.microsoft.com/windows-server/virtualization/hyper-v/get-started/install-hyper-v).
2. Con la máquina apagada, abre Configuración > Unidad de DVD. Si falta Windows, selecciona una ISO oficial de [Windows 11](https://www.microsoft.com/software-download/windows11). En Firmware, coloca el DVD antes del disco para la primera instalación. Conserva el disco virtual existente.
3. El servidor usa WSL2 dentro de esta máquina. Antes de encenderla, abre PowerShell como administrador en el computador anfitrión y ejecuta:

```powershell
Set-VMProcessor -VMName "OpenMultiPOS-QA" -ExposeVirtualizationExtensions $true
```

La máquina debe estar apagada para este cambio. Es la configuración de [virtualización anidada de Microsoft](https://learn.microsoft.com/windows-server/virtualization/hyper-v/enable-nested-virtualization); no reinicia el computador anfitrión.

4. En Hyper-V elige Conectar y después Iniciar. Pulsa una tecla si aparece el mensaje para arrancar desde DVD. Si aparece Windows Setup, completa la instalación dentro de la máquina. Si aparece directamente el escritorio, Windows ya está instalado. Microsoft documenta las opciones de medios en [crear una máquina virtual](https://learn.microsoft.com/windows-server/virtualization/hyper-v/get-started/create-a-virtual-machine-in-hyper-v).
5. En el escritorio invitado, instala las actualizaciones de Windows. Si falta internet, revisa Configuración > Adaptador de red de la máquina y su conmutador virtual autorizado. El controlador OpenMultiPOS permite Preparar Windows para instalar WSL; cualquier reinicio solicitado se realiza dentro de la máquina invitada. Después se prueban allí los paquetes con datos ficticios.

Mantén la máquina apagada cuando no se use para evitar consumo de memoria y CPU. No copies datos reales del negocio a este entorno de aceptación. Si aparece un error, conserva su texto exacto; no borres el disco ni recrees la máquina para resolverlo.
