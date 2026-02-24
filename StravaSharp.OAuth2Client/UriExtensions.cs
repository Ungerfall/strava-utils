namespace StravaSharp.OAuth2Client;

public static class UriExtensions
{
    extension(string input)
    {
        public IDictionary<string, string> ParseQueryString()
        {
            if (input.StartsWith("?"))
            {
                input = input.Substring(1);
            }

            return input.Split('&')
                .Select(static keyValuePairs =>
                {
                    string[] keyAndValue = keyValuePairs.Split('=');
                    return new KeyValuePair<string, string>(keyAndValue[0], keyAndValue[1]);
                })
                .ToDictionary(static x => x.Key, static x => x.Value);
        }
    }
}
