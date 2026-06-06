from generator import asar

NAMESPACE = "Default"

TxSignal_IV = asar.factory.ConstantTemplate('TxSignal_IV', NAMESPACE, 0)
RxSignal_IV = asar.factory.ConstantTemplate('RxSignal_IV', NAMESPACE, 0)

TxSignal_I = asar.factory.SenderReceiverInterfaceTemplate('TxSignal_I', NAMESPACE, asar.platform.ImplementationTypes.uint8)
RxSignal_I = asar.factory.SenderReceiverInterfaceTemplate('RxSignal_I', NAMESPACE, asar.platform.ImplementationTypes.uint8)
COM_D = []
COM_D.append('TxSignal')
COM_D.append('RxSignal')
