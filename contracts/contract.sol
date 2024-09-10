// SPDX-License-Identifier: MIT
pragma solidity ^0.8.10;

contract DeviceTrackingSystem {
    address public owner;

    constructor() {
        owner = msg.sender;
    }

    modifier onlyOwner() {
        require(msg.sender == owner, "Only the contract owner can call this function");
        _;
    }

    // User Management
    enum UserType {
        Manufacturer,
        Distributor,
        Retailer,
        Consumer,
        Refurbisher,
        Recycler,
        Environment,
        Government
    }

    struct User {
        uint256 telegramId;
        UserType userType;
        bool isRegistered;
        address walletAddress;
    }

    mapping(uint256 => User) public users; // Telegram ID to User
    mapping(address => uint256) public addressToTelegramId; // Ethereum address to Telegram ID

    event UserRegistered(uint256 telegramId, UserType userType, address walletAddress);

    // Device Management
    enum DeviceStatus {
        InRepair,
        Active,
        Repaired,
        ToDispose,
        Disposable
    }

    struct Component {
        string componentName;
        string material;
    }

    struct LifecycleEvent {
        string eventDescription;
        uint256 timestamp;
    }

    struct DisposalEvent {
        string disposalMethod;
        string disposalDate;
        string location;
        string disposedBy;
    }

    struct AdditionalDetails {
        bool is5GCapable;
        uint256 releaseDate;
        string os;
        string chipset;
        uint16 phoneMemory;
        string batteryType;
        string condition;
        uint8 expectedLifecycle;
        uint256 achievedLifecycle;
        uint256 weight;
        string deviceType;
    }

    struct EWastePassport {
        string phoneName;
        string manufacturer;
        uint256 imeiNumber;
        uint256 manufactureDate;
        uint256 expectedLifecycle;
        bool isBatteryReplaceable;
        Component[] components;
        LifecycleEvent[] lifecycleEvents;
        DisposalEvent disposalEvent;
        AdditionalDetails additionalDetails;
    }

    mapping(uint256 => bool) public registeredDevices;
    mapping(uint256 => EWastePassport) public passports;
    mapping(uint256 => DeviceStatus) public deviceStatuses;

    event DeviceRegistered(uint256 imeiNumber);
    event DeviceCreated(
        string deviceName,
        string deviceType,
        string manufacturer,
        uint256 imeiNumber,
        uint256 manufactureDate,
        uint256 expectedLifecycle,
        bool isBatteryReplaceable
    );
    event LifecycleEventAdded(uint256 imeiNumber, string eventDescription);
    event DisposalEventAdded(uint256 imeiNumber, string disposalMethod, string disposalDate, string location);

    // User Registration Functions
    function registerUser(uint256 _telegramId, UserType _userType, address _walletAddress) public {
        require(!users[_telegramId].isRegistered, "User already registered!");
        users[_telegramId] = User(_telegramId, _userType, true, _walletAddress);
        addressToTelegramId[_walletAddress] = _telegramId;
        emit UserRegistered(_telegramId, _userType, _walletAddress);
    }

    function isUserRegistered(uint256 _telegramId) public view returns (bool) {
        return users[_telegramId].isRegistered;
    }

    function getUserType(uint256 _telegramId) public view returns (UserType) {
        require(users[_telegramId].isRegistered, "User not registered!");
        return users[_telegramId].userType;
    }

    function updateUserType(uint256 _telegramId, UserType _newType) public onlyOwner {
        require(users[_telegramId].isRegistered, "User not registered!");
        users[_telegramId].userType = _newType;
    }

    function isUserAuthorized(address _userAddress) public view returns (bool) {
        uint256 telegramId = addressToTelegramId[_userAddress];
        require(users[telegramId].isRegistered, "User not registered!");
        UserType userType = users[telegramId].userType;
        return userType == UserType.Manufacturer || userType == UserType.Distributor || userType == UserType.Retailer
            || userType == UserType.Consumer || userType == UserType.Refurbisher || userType == UserType.Recycler;
    }

    // Device Functions
    function registerDevice(uint256 _imeiNumber) public {
        require(isUserAuthorized(msg.sender), "User not authorized!");
        require(!registeredDevices[_imeiNumber], "Device already registered!");
        registeredDevices[_imeiNumber] = true;
        emit DeviceRegistered(_imeiNumber);
    }

    function createNewDevice(
        uint256 _imeiNumber,
        string memory _phoneName,
        string memory _manufacturer,
        uint256 _manufactureDate,
        uint256 _expectedLifecycle,
        bool _isBatteryReplaceable,
        bool _is5GCapable,
        uint256 _releaseDate,
        string memory _os,
        string memory _chipset,
        uint16 _phoneMemory,
        string memory _batteryType,
        string memory _condition,
        uint8 _additionalExpectedLifecycle,
        uint256 _achievedLifecycle,
        uint256 _weight,
        string memory _deviceType
    ) public {
        require(isUserAuthorized(msg.sender), "User not authorized!");
        require(registeredDevices[_imeiNumber], "Device not registered!");

        // Create the device passport
        EWastePassport storage newPassport = passports[_imeiNumber];
        newPassport.phoneName = _phoneName;
        newPassport.manufacturer = _manufacturer;
        newPassport.imeiNumber = _imeiNumber;
        newPassport.manufactureDate = _manufactureDate;
        newPassport.expectedLifecycle = _expectedLifecycle;
        newPassport.isBatteryReplaceable = _isBatteryReplaceable;
        newPassport.additionalDetails = AdditionalDetails({
            is5GCapable: _is5GCapable,
            releaseDate: _releaseDate,
            os: _os,
            chipset: _chipset,
            phoneMemory: _phoneMemory,
            batteryType: _batteryType,
            condition: _condition,
            expectedLifecycle: _additionalExpectedLifecycle,
            achievedLifecycle: _achievedLifecycle,
            weight: _weight,
            deviceType: _deviceType
        });

        emit DeviceCreated(
            _phoneName,
            _deviceType,
            _manufacturer,
            _imeiNumber,
            _manufactureDate,
            _expectedLifecycle,
            _isBatteryReplaceable
        );
    }

    function setDeviceStatus(uint256 _imeiNumber, DeviceStatus _status) public {
        require(isUserAuthorized(msg.sender), "User not authorized!");
        require(registeredDevices[_imeiNumber], "Device not registered!");
        deviceStatuses[_imeiNumber] = _status;
    }

    // Event Management Functions
    function addLifecycleEvent(uint256 _imeiNumber, string memory _eventDescription) public {
        require(isUserAuthorized(msg.sender), "User not authorized!");
        require(registeredDevices[_imeiNumber], "Device not registered!");

        LifecycleEvent memory newEvent =
            LifecycleEvent({eventDescription: _eventDescription, timestamp: block.timestamp});
        passports[_imeiNumber].lifecycleEvents.push(newEvent);
        emit LifecycleEventAdded(_imeiNumber, _eventDescription);
    }

    function addDisposalEvent(
        uint256 _imeiNumber,
        string memory _disposalMethod,
        string memory _disposalDate,
        string memory _disposalLocation
    ) public {
        require(isUserAuthorized(msg.sender), "User not authorized!");
        require(registeredDevices[_imeiNumber], "Device not registered!");

        passports[_imeiNumber].disposalEvent = DisposalEvent({
            disposalMethod: _disposalMethod,
            disposalDate: _disposalDate,
            location: _disposalLocation,
            disposedBy: addressToString(msg.sender)
        });

        emit DisposalEventAdded(_imeiNumber, _disposalMethod, _disposalDate, _disposalLocation);
    }

    function addressToString(address _address) private pure returns (string memory) {
        bytes32 value = bytes32(uint256(uint160(_address)));
        bytes memory alphabet = "0123456789abcdef";
        bytes memory str = new bytes(42);
        str[0] = "0";
        str[1] = "x";
        for (uint256 i = 0; i < 20; i++) {
            str[2 + i * 2] = alphabet[uint8(value[i + 12] >> 4)];
            str[3 + i * 2] = alphabet[uint8(value[i + 12] & 0x0f)];
        }
        return string(str);
    }

    // Getter Functions
    function getLifecycleEventsCount(uint256 _imeiNumber) public view returns (uint256) {
        return passports[_imeiNumber].lifecycleEvents.length;
    }

    function getLifecycleEvent(uint256 _imeiNumber, uint256 index)
        public
        view
        returns (string memory eventDescription, uint256 timestamp)
    {
        require(index < passports[_imeiNumber].lifecycleEvents.length, "Index out of bounds");
        LifecycleEvent memory lifecycleEvent = passports[_imeiNumber].lifecycleEvents[index];
        return (lifecycleEvent.eventDescription, lifecycleEvent.timestamp);
    }

    function getDisposalDetails(uint256 _imeiNumber)
        public
        view
        returns (string memory, string memory, string memory, string memory)
    {
        DisposalEvent memory disposal = passports[_imeiNumber].disposalEvent;
        return (disposal.disposalMethod, disposal.disposalDate, disposal.location, disposal.disposedBy);
    }

    function getPassportByIMEI(uint256 _imeiNumber) public view returns (EWastePassport memory) {
        return passports[_imeiNumber];
    }
}
