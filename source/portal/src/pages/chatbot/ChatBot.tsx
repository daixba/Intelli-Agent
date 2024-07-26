import React, { useContext, useEffect, useState } from 'react';
import CommonLayout from 'src/layout/CommonLayout';
import Message from './components/Message';
import useAxiosRequest from 'src/hooks/useAxiosRequest';
import { useTranslation } from 'react-i18next';
import {
  Box,
  Button,
  Select,
  SelectProps,
  StatusIndicator,
  Textarea,
  Toggle,
} from '@cloudscape-design/components';
import useWebSocket, { ReadyState } from 'react-use-websocket';
import { identity } from 'lodash';
import ConfigContext from 'src/context/config-context';
import { useAuth } from 'react-oidc-context';
import {
  LLM_BOT_CHAT_MODE_LIST,
} from 'src/utils/const';
import { v4 as uuidv4 } from 'uuid';
import { MessageDataType, SessionMessage } from 'src/types';

interface MessageType {
  type: 'ai' | 'human';
  message: {
    data: string;
    monitoring: string;
  };
}

interface ChatBotProps {
  historySessionId?: string;
}

const ChatBot: React.FC<ChatBotProps> = (props: ChatBotProps) => {
  const { historySessionId } = props;
  const config = useContext(ConfigContext);
  const { t } = useTranslation();
  const auth = useAuth();
  const [loadingHistory, setLoadingHistory] = useState(false);
  const [messages, setMessages] = useState<MessageType[]>([
    {
      type: 'ai',
      message: {
        data: t('welcomeMessage'),
        monitoring: '',
      },
    },
  ]);
  const [userMessage, setUserMessage] = useState('');
  const { lastMessage, sendMessage, readyState } = useWebSocket(
    `${config?.websocket}?idToken=${auth.user?.id_token}`,
    {
      onOpen: () => console.log('opened'),
      //Will attempt to reconnect on all close events, such as server shutting down
      shouldReconnect: () => true,
    },
  );
  const [currentAIMessage, setCurrentAIMessage] = useState('');
  const [currentMonitorMessage, setCurrentMonitorMessage] = useState('');
  const [aiSpeaking, setAiSpeaking] = useState(false);
  const [chatModeOption, setChatModeOption] = useState<SelectProps.Option>(
    LLM_BOT_CHAT_MODE_LIST[0],
  );
  const [useChatHistory, setUseChatHistory] = useState(true);
  const [enableTrace, setEnableTrace] = useState(true);
  const [showTrace, setShowTrace] = useState(true);


  const [sessionId, setSessionId] = useState(historySessionId);
  const [botId, setBotId] = useState('');
  const [showMessageError, setShowMessageError] = useState(false);
  // const [googleAPIKeyError, setGoogleAPIKeyError] = useState(false);
  const [isMessageEnd, setIsMessageEnd] = useState(false);

  const connectionStatus = {
    [ReadyState.CONNECTING]: 'loading',
    [ReadyState.OPEN]: 'success',
    [ReadyState.CLOSING]: 'closing',
    [ReadyState.CLOSED]: 'error',
    [ReadyState.UNINSTANTIATED]: 'pending',
  }[readyState];

  // Define an async function to get the data
  const fetchData = useAxiosRequest();

    const getBotList = async () => {
    try {
      console.log("get bots")
      const data = await fetchData({
        url: 'v1/bots',
        method: 'get',
      });
      console.log(data)
      setBotId(data[0].bot_id)
    } catch (error) {
      console.error(error);
    }
  };

  const getSessionHistoryById = async () => {
    try {
      setLoadingHistory(true);
      const data = await fetchData({
        url: `ddb/list-messages`,
        method: 'get',
        params: {
          session_id: historySessionId,
          page_size: 9999,
          max_items: 9999,
        },
      });
      const sessionMessage: SessionMessage[] = data.Items;
      setMessages(
        sessionMessage.map((msg) => {
          let messageContent = msg.content;
          // Handle AI images message
          if (msg.role === 'ai' && msg.additional_kwargs.figure.length > 0) {
            msg.additional_kwargs.figure.forEach((item) => {
              messageContent += ` \n ![${item.content_type}](/${encodeURIComponent(item.figure_path)})`;
            });
          }
          return {
            type: msg.role,
            message: {
              data: messageContent,
              monitoring: '',
            },
          };
        }),
      );
      setLoadingHistory(false);
    } catch (error) {
      console.error(error);
      return [];
    }
  };

  useEffect(() => {
    if (historySessionId) {
      // get session history by id
      getSessionHistoryById();
    } else {
      setSessionId(uuidv4());
    }
    getBotList();
  }, []);

  useEffect(() => {
    if (enableTrace) {
      setShowTrace(true);
    } else {
      setShowTrace(false);
    }
  }, [enableTrace]);

  const handleAIMessage = (message: MessageDataType) => {
    console.info('handleAIMessage:', message);
    if (message.message_type === 'START') {
      console.info('message started');
    } else if (message.message_type === 'CHUNK') {
      setCurrentAIMessage((prev) => {
        return prev + (message?.message?.content ?? '');
      });
    } else if (message.message_type === 'CONTEXT') {
      // handle context message
      if (message.ddb_additional_kwargs?.figure?.length > 0) {
        message.ddb_additional_kwargs.figure.forEach((item) => {
          setCurrentAIMessage((prev) => {
            return (
              prev +
              ` \n ![${item.content_type}](/${encodeURIComponent(item.figure_path)})`
            );
          });
        });
      }
    } else if (message.message_type === 'END') {
      setIsMessageEnd(true);
    }
  };

  useEffect(() => {
    if (lastMessage !== null) {
      const message: MessageDataType = JSON.parse(lastMessage.data);
      if (message.message_type === 'MONITOR') {
        setCurrentMonitorMessage((prev) => {
          return prev + (message?.message ?? '');
        });
      } else {
        handleAIMessage(message);
      }
    }
  }, [lastMessage]);

  useEffect(() => {
    if (isMessageEnd) {
      setAiSpeaking(false);
      setMessages((prev) => {
        return [
          ...prev,
          {
            type: 'ai',
            message: {
              data: currentAIMessage,
              monitoring: currentMonitorMessage,
            },
          },
        ];
      });
    }
  }, [isMessageEnd]);

  const handleClickSendMessage = () => {
    if (aiSpeaking) {
      return;
    }
    if (!userMessage.trim()) {
      setShowMessageError(true);
      return;
    }
    // validate websocket status
    if (readyState !== ReadyState.OPEN) {
      return;
    }

    setUserMessage('');
    setAiSpeaking(true);
    setCurrentAIMessage('');
    setCurrentMonitorMessage('');
    setIsMessageEnd(false);
    // if (useWebSearch && !googleAPIKey.trim()) {
    //   setGoogleAPIKeyError(true);
    //   return;
    // }
    let message = {
      query: userMessage,
      entry_type: "common",
      session_id: sessionId,
      user_profile:  chatModeOption.value,
      use_history: useChatHistory,
      enable_trace: enableTrace,
      bot_id: botId,
    };


    console.info('send message:', message);
    sendMessage(JSON.stringify(message));
    setMessages((prev) => {
      return [
        ...prev,
        {
          type: 'human',
          message: {
            data: userMessage,
            monitoring: '',
          },
        },
      ];
    });
    setUserMessage('');
  };



  return (
    <CommonLayout
      isLoading={loadingHistory}
      activeHref={!historySessionId ? '/' : '/sessions'}
    >
      <div className="chat-container mt-10">
        <div className="chat-message flex-v flex-1 gap-10">
          {messages.map((msg, index) => (
            <Message
              showTrace={showTrace}
              key={identity(index)}
              type={msg.type}
              message={msg.message}
            />
          ))}
          {aiSpeaking && (
            <Message
              aiSpeaking={aiSpeaking}
              type="ai"
              showTrace={showTrace}
              message={{
                data: currentAIMessage,
                monitoring: currentMonitorMessage,
              }}
            />
          )}
        </div>

        <div className="flex-v gap-10">
          <div className="flex gap-5 send-message">
            <Select
              options={LLM_BOT_CHAT_MODE_LIST}
              selectedOption={chatModeOption}
              onChange={({ detail }) => {
                setChatModeOption(detail.selectedOption);
              }}
            />
            <div className="flex-1 pr">
              <Textarea
                invalid={showMessageError}
                rows={1}
                value={userMessage}
                placeholder={t('typeMessage')}
                onChange={(e) => {
                  setShowMessageError(false);
                  setUserMessage(e.detail.value);
                }}
                onKeyDown={(e) => {
                  if (e.detail.key === 'Enter') {
                    e.preventDefault();
                    handleClickSendMessage();
                  }
                }}
              />
            </div>
            <div>
              <Button
                disabled={aiSpeaking || readyState !== ReadyState.OPEN}
                onClick={() => {
                  handleClickSendMessage();
                }}
              >
                {t('button.send')}
              </Button>
            </div>
          </div>
          <div>
            <div className="flex space-between">
              <div className="flex gap-10 align-center">
                <Toggle
                  onChange={({ detail }) => setUseChatHistory(detail.checked)}
                  checked={useChatHistory}
                >
                  {t('multiRound')}
                </Toggle>
                <Toggle
                  onChange={({ detail }) => setEnableTrace(detail.checked)}
                  checked={enableTrace}
                >
                  {t('enableTrace')}
                </Toggle>
                {enableTrace && (
                  <Toggle
                    onChange={({ detail }) => setShowTrace(detail.checked)}
                    checked={showTrace}
                  >
                    {t('showTrace')}
                  </Toggle>
                )}
                {/*{chatModeOption.value === 'agent' && (*/}
                {/*  <Toggle*/}
                {/*    onChange={({ detail }) => setOnlyRAGTool(detail.checked)}*/}
                {/*    checked={onlyRAGTool}*/}
                {/*  >*/}
                {/*    {t('onlyUseRAGTool')}*/}
                {/*  </Toggle>*/}
                {/*)}*/}

                {/*
                <Toggle
                  onChange={({ detail }) => {
                    setGoogleAPIKeyError(false);
                    setUseWebSearch(detail.checked);
                  }}
                  checked={useWebSearch}
                >
                  Enable WebSearch
                </Toggle>
                {useWebSearch && (
                  <div style={{ minWidth: 300 }}>
                    <Input
                      invalid={googleAPIKeyError}
                      placeholder="Please input your Google API key"
                      value={googleAPIKey}
                      onChange={({ detail }) => {
                        setGoogleAPIKeyError(false);
                        setGoogleAPIKey(detail.value);
                      }}
                    />
                  </div>
                )}
                */}
              </div>
              <div className="flex align-center gap-10">
                <Box variant="p">{t('server')}: </Box>
                <StatusIndicator type={connectionStatus as any}>
                  {t(connectionStatus)}
                </StatusIndicator>
              </div>
            </div>
          </div>
        </div>
      </div>
    </CommonLayout>
  );
};

export default ChatBot;
